"""Offline regression checks for audit state, persistence, filtering and site editing."""
from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from app.components import audit_data, inference
from app.components.inference import InferenceResult
from app.components.mockup_ui import CATEGORY_SET, run_mock_classifier
from waste_audit.utils import config

ROOT = Path(__file__).resolve().parents[1]


def app(page):
    return AppTest.from_file(str(ROOT / 'app/main.py')).switch_page(f'pages/{page}').run()


def row(**changes):
    record = dict(site_id='example-lab-220',stream_type='recycling',bag_id='TEST',weight_lb=4,
                  scanned_at='2026-10-01T12:00:00Z',contamination_pct=8,inference_source='model',
                  categories=[dict(category='paper',corrected_pct=34),dict(category='plastic',corrected_pct=28),
                              dict(category='metal',corrected_pct=18),dict(category='glass',corrected_pct=12),
                              dict(category='trash',corrected_pct=6),dict(category='other',corrected_pct=2)])
    return {**record, **changes}


def test_record_loading_filtering_and_provenance(tmp_path):
    path = tmp_path/'audits.jsonl'
    for record in [row(),row(inference_source='mock',contamination_pct=20),row(inference_source=None),
                   row(weight_lb='bad',categories='bad'),row(scanned_at='bad'),row(contamination_pct=float('inf'))]:
        with path.open('a') as f:
            f.write(json.dumps(record)+'\n')
    with path.open('a') as f:
        f.write('[]\nnot-json\n')
    records, skipped = audit_data.read_audits(path)
    assert len(records)==4 and skipped==4
    first, last = dt.date(2026,10,1),dt.date(2026,10,2)
    assert len(audit_data.filter_audits(records,first,last))==2
    assert len(audit_data.filter_audits(records,first,last,include_mock=True,include_legacy=True))==4
    assert not audit_data.filter_audits(records,first,last,sites=['missing'])
    assert not audit_data.filter_audits(records,first,last,streams=['compost'])
    assert not audit_data.filter_audits(records,last,last)
    assert records[-1]['weight_lb'] is None


def test_category_profiles_missing_keys_and_zero():
    profile = audit_data.category_profile([row(categories=[dict(category='paper',corrected_pct=100)]),
                                           row(categories=[dict(category='trash',corrected_pct=100)])])
    assert profile=={'paper':50,'trash':50}
    assert audit_data.top_contaminant([row()])=='Trash'
    assert audit_data.top_contaminant([row(categories=[])]) is None
    assert audit_data.top_contaminant([row(categories=[dict(category='paper',corrected_pct=100),dict(category='trash',corrected_pct=0)])])=='None (0%)'


def test_persistence_and_storage_failure(tmp_path):
    path = tmp_path/'exports/audits.jsonl'
    audit_data.save_audit(row(),path)
    assert audit_data.read_audits(path)[0][0]['bag_id']=='TEST'
    with pytest.raises(OSError):
        audit_data.save_audit(row(),tmp_path)


def test_site_validation_and_atomic_update(tmp_path):
    path = tmp_path/'sites.yaml'
    path.write_text('sites: []\nsite_types: [lab, office]\ncustom_setting: preserved\n')
    site = dict(site_id='test-lab',site_name='Test Lab',site_type='lab',bin_type='recycling',gps=None)
    audit_data.save_site(site,path,creating=True)
    with pytest.raises(ValueError,match='already exists'):
        audit_data.save_site(site,path,creating=True)
    with pytest.raises(ValueError,match='latitude'):
        audit_data.save_site(dict(site,gps=dict(latitude=100,longitude=0)),path)
    with pytest.raises(ValueError,match='name'):
        audit_data.save_site(dict(site,site_name=' '),path)
    with pytest.raises(ValueError,match='Site ID'):
        audit_data.save_site(dict(site,site_id='../invalid'),path,creating=True)
    audit_data.save_site(dict(site,site_name='Renamed',bin_configuration='Blue bin'),path)
    loaded = config.load_yaml(path)
    assert loaded['custom_setting']=='preserved'
    assert loaded['sites'][0]['site_id']=='test-lab'
    assert loaded['sites'][0]['site_name']=='Renamed'


def test_audit_review_rerun_and_save_failure(monkeypatch):
    image = io.BytesIO()
    Image.new('RGB',(32,32),'green').save(image,format='PNG')
    at = AppTest.from_file(str(ROOT/'app/main.py')).switch_page('pages/1_Audit.py')
    for key, value in dict(step='capture',photo_bytes=image.getvalue(),bag_id='TEST',weight=4.2).items():
        at.session_state[key]=value
    monkeypatch.setattr(inference,'run_classifier', lambda *args: InferenceResult(run_mock_classifier(),'mock'))
    at.run()
    assert not at.exception
    at.button[0].click().run()
    assert at.session_state['step']=='results'
    at.number_input(key='cat_input_paper').set_value(run_mock_classifier()['paper'] - 2).run()
    assert at.button[-1].disabled
    at.number_input(key='cat_input_soft_plastics').set_value(run_mock_classifier()['soft_plastics'] + 2).run()
    assert not at.button[-1].disabled
    at.button[0].click().run()
    assert at.session_state['corrected']['paper']==run_mock_classifier()['paper'] - 2
    assert at.session_state['corrected']['soft_plastics']==run_mock_classifier()['soft_plastics'] + 2
    def fail(record):
        raise OSError('Test disk failure')
    monkeypatch.setattr(audit_data,'save_audit',fail)
    at.button[-1].click().run()
    assert at.session_state['step']=='results'
    assert 'not saved' in at.error[0].value
    saved=[]
    monkeypatch.setattr(audit_data,'save_audit',saved.append)
    at.button[-1].click().run()
    assert at.session_state['step']=='saved'
    assert len(saved)==1 and saved[0]['hazard_flagged'] is None and saved[0]['inference_source']=='mock'
    assert saved[0]['category_set'] == CATEGORY_SET
    assert sum(c['est_weight_lb'] for c in saved[0]['categories']) == pytest.approx(4.2, abs=.01)
    from waste_audit.pipeline.weight import estimate_weights
    expected = estimate_weights(at.session_state['corrected'], CATEGORY_SET, bag_weight_lb=4.2)
    for category in saved[0]['categories']:
        assert category['est_weight_pct'] == pytest.approx(expected.weight_pct[category['category']], abs=.01)
    # Fresh render avoids AppTest's stale widget tree after a rerun removes review inputs.
    fresh=AppTest.from_file(str(ROOT/'app/main.py')).switch_page('pages/1_Audit.py')
    fresh.session_state['step']='saved'
    fresh.run().button[0].click().run()
    assert fresh.session_state['step']=='capture'
    assert fresh.text_input[0].value=='' and fresh.number_input[0].value==0
    assert fresh.session_state['photo_bytes'] is None
    assert not fresh.exception


def test_dashboard_filters_and_unavailable_hazards(monkeypatch,tmp_path):
    path = tmp_path/'audits.jsonl'
    for record in [row(),row(site_id='example-cafe-union',contamination_pct=40),row(inference_source='mock',contamination_pct=90)]:
        audit_data.save_audit(record,path)
    monkeypatch.setattr(audit_data,'AUDITS_PATH',path)
    at=app('2_Dashboard.py')
    assert not at.exception
    assert at.metric[0].value=='24.0%' and at.metric[1].value=='2'
    assert at.metric[2].value=='Unavailable'
    at.multiselect[0].set_value(['example-lab-220']).run()
    assert at.metric[0].value=='8.0%' and at.metric[1].value=='1'
    at.checkbox[0].check().run()
    assert at.metric[0].value=='49.0%' and at.metric[1].value=='2'
    at.multiselect[1].set_value(['compost']).run()
    assert at.metric[0].value=='—' and at.metric[1].value=='0'
    assert not at.exception


def test_site_form_persistence_and_search(monkeypatch,tmp_path):
    path=tmp_path/'sites.yaml'
    path.write_text('sites: []\nsite_types: [lab, office]\n')
    original=config.load_sites
    monkeypatch.setattr(config,'load_sites',lambda: original(path))
    monkeypatch.setattr(audit_data,'SITES_PATH',path)
    monkeypatch.setattr(audit_data,'AUDITS_PATH',tmp_path/'empty.jsonl')
    at=app('3_Sites.py')
    assert not at.exception
    at.text_input[1].set_value('test-lab')
    at.text_input[2].set_value('Test Lab')
    at.button[-1].click().run()
    assert original(path)['test-lab']['site_name']=='Test Lab'
    at=app('3_Sites.py')
    at.text_input[0].set_value('no match').run()
    assert any('No sites match' in item.value for item in at.info)
    assert not at.exception


def test_invalid_photo_and_discard():
    at=AppTest.from_file(str(ROOT/'app/main.py')).switch_page('pages/1_Audit.py')
    for key,value in dict(photo_bytes=b'not an image',bag_id='TEST',weight=3.0).items():
        at.session_state[key]=value
    at.run()
    assert at.error and 'cannot be opened' in at.error[0].value
    assert at.button[0].disabled
    image=io.BytesIO()
    Image.new('RGB',(32,32),'green').save(image,format='PNG')
    review=AppTest.from_file(str(ROOT/'app/main.py')).switch_page('pages/1_Audit.py')
    for key,value in dict(step='results',photo_bytes=image.getvalue(),model_output=run_mock_classifier(),
                          corrected=run_mock_classifier(),inference_source='mock',bag_id='TEST',weight=3.0).items():
        review.session_state[key]=value
    review.run()
    review.button[-2].click().run()
    assert review.session_state['step']=='capture'
    assert review.session_state['photo_bytes'] is None
    assert review.session_state['corrected'] is None
    assert not review.exception


@pytest.mark.parametrize("category_set", ["fine", "coarse"])
@pytest.mark.parametrize("stream", ["recycling", "compost"])
def test_sort_categories_review_save_and_dashboard(monkeypatch, tmp_path, category_set, stream):
    """Both category sets survive review, persistence and analytics, including n/a scores."""
    from app.components import mockup_ui
    from waste_audit.pipeline.weight import estimate_weights

    categories = mockup_ui._build_category_config(category_set)
    breakdown = {c['key']: c['default_pct'] for c in categories}
    monkeypatch.setattr(mockup_ui, 'CATEGORY_SET', category_set)
    monkeypatch.setattr(mockup_ui, 'MOCKUP_CATEGORIES', categories)
    # The helper's default was bound at import; use the active test configuration explicitly.
    calculate = mockup_ui.calculate_stream_contamination
    monkeypatch.setattr(mockup_ui, 'calculate_stream_contamination',
                        lambda stream, values: calculate(stream, values, category_set))
    path = tmp_path / 'audits.jsonl'
    monkeypatch.setattr(audit_data, 'AUDITS_PATH', path)
    image = io.BytesIO()
    Image.new('RGB', (32, 32), 'green').save(image, format='PNG')
    at = AppTest.from_file(str(ROOT / 'app/main.py')).switch_page('pages/1_Audit.py')
    for key, value in dict(step='results', photo_bytes=image.getvalue(), model_output=breakdown,
                           corrected=dict(breakdown), inference_source='model',
                           bag_id='MERGE-TEST', weight=5.0, stream_type=stream,
                           site_id='example-lab-220').items():
        at.session_state[key] = value
    at.run()
    assert not at.exception
    assert len(at.number_input) == len(categories)
    at.button[-1].click().run()
    assert not at.exception and at.session_state['step'] == 'saved'
    records, skipped = audit_data.read_audits(path)
    assert skipped == 0 and len(records) == 1
    record = records[0]
    assert record['category_set'] == category_set
    expected = estimate_weights(breakdown, category_set, bag_weight_lb=5.0)
    assert sum(c['est_weight_lb'] for c in record['categories']) == pytest.approx(5.0, abs=.01)
    for category in record['categories']:
        assert category['weight_factor'] == expected.factors[category['category']]
        assert category['est_weight_pct'] == pytest.approx(expected.weight_pct[category['category']], abs=.01)
    if stream == 'compost':
        assert record['contamination_pct'] is None
    else:
        assert record['contamination_pct'] == calculate(stream, breakdown, category_set)[0]
        assert audit_data.top_contaminant(records) is not None
    dashboard = app('2_Dashboard.py')
    assert not dashboard.exception
    assert dashboard.metric[1].value == '1'
    assert dashboard.metric[0].value == ('—' if stream == 'compost' else f"{record['contamination_pct']:.1f}%")
    assert len(dashboard.get('download_button')) == 1


def test_missing_or_invalid_contamination_still_rejected(tmp_path):
    path = tmp_path / 'audits.jsonl'
    missing = row()
    del missing['contamination_pct']
    for record in [missing, row(contamination_pct=None), row(contamination_pct=None, category_set='fine'),
                   row(contamination_pct=None, category_set='fine', stream_type='compost')]:
        audit_data.save_audit(record, path)
    records, skipped = audit_data.read_audits(path)
    assert skipped == 3 and len(records) == 1
    assert records[0]['contamination_pct'] is None
