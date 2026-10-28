"""Add clearly labeled, reproducible demo audits without replacing existing data.

Run from the repository root: python scripts/seed_demo_audits.py
Dashboard: enable 'Include labeled mock audits' to view the generated records.
Repeated runs with the same date/seed/count skip existing demo bag IDs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / 'src'):
    sys.path.insert(0, str(path))

from app.components.audit_data import AUDITS_PATH, save_audit, save_site
from app.components.mockup_ui import calculate_stream_contamination
from waste_audit.utils.config import load_sites

CATEGORIES = ('paper', 'plastic', 'metal', 'glass', 'trash', 'other')
DEMO_SITES = (
    ('demo-office-admin', 'DEMO · Administration Office', 'office', 'recycling'),
    ('demo-dorm-north', 'DEMO · North Residence Hall', 'dorm', 'recycling'),
    ('demo-outdoor-quad', 'DEMO · Campus Quad', 'outdoor_public', 'landfill'),
    ('demo-cafe-dining', 'DEMO · Dining Hall', 'food_service', 'compost'),
    ('demo-lab-materials', 'DEMO · Materials Laboratory', 'lab', 'recycling'),
    ('demo-other-events', 'DEMO · Event Collection Point', 'other', 'landfill'),
)


def percentages(values):
    """Largest-remainder rounding keeps six displayed shares at exactly 100%."""
    total = sum(values)
    scaled = [v / total * 1000 for v in values]
    tenths = [int(v) for v in scaled]
    for i in sorted(range(len(values)), key=lambda i: scaled[i] - tenths[i], reverse=True)[:1000-sum(tenths)]:
        tenths[i] += 1
    return dict(zip(CATEGORIES, [v / 10 for v in tenths]))


def generate(sites, count, days, end, seed):
    rng = random.Random(seed)
    site_ids = sorted(sites)
    start = end - dt.timedelta(days=days - 1)
    for i in range(count):
        day_index = min(days-1, i * days // count)
        timestamp = dt.datetime.combine(start + dt.timedelta(days=day_index), dt.time(rng.randrange(8,18),rng.randrange(60)), tzinfo=dt.timezone.utc)
        sid = site_ids[i % len(site_ids)]
        site = sites[sid]
        stream = site.get('bin_type', 'recycling') if rng.random() < .7 else rng.choice(('recycling','compost','landfill'))
        bases = {'recycling':[45,28,12,8,5,2], 'compost':[66,5,2,1,21,5], 'landfill':[18,23,8,5,38,8]}[stream]
        # Broad provisional material categories, with site effects and improving seasonal purity.
        values = [max(.2, rng.gauss(base, base*.3)) for base in bases]
        site_factor = 1 + (site_ids.index(sid) % 4) * .18
        progress = day_index / max(1, days-1)
        contaminants = {'recycling':(4,5), 'compost':(1,2,3,4), 'landfill':()}[stream]
        spike = 2.5 if i % 31 == 0 else 1
        for k in contaminants:
            values[k] *= site_factor * (1.6 - .8*progress) * spike
        original = percentages(values)
        corrected = dict(original)
        if i % 4 == 0:
            donor = max(corrected, key=corrected.get)
            receiver = rng.choice([k for k in CATEGORIES if k != donor])
            shift = round(min(corrected[donor], rng.uniform(.5,4)),1)
            corrected[donor] = round(corrected[donor]-shift,1)
            corrected[receiver] = round(corrected[receiver]+shift,1)
        contamination, _ = calculate_stream_contamination(stream, corrected)
        yield dict(bag_id=f'DEMO-{end:%Y%m%d}-{seed}-{i+1:04d}',
                   weight_lb=round(rng.uniform(1.2,24.8),1),site_id=sid,stream_type=stream,
                   contamination_pct=contamination,hazard_flagged=None,hazard_assessed=False,reviewed=True,
                   inference_source='mock',inference_label='Synthetic demo data — no classifier call',
                   demo_dataset='portal-demo-v1',demo_seed=seed,scanned_at=timestamp.isoformat(),
                   categories=[dict(category=k,label=k.title(),original_pct=original[k],corrected_pct=corrected[k],
                                    edited=abs(original[k]-corrected[k])>.001) for k in CATEGORIES])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=360)
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--end-date', type=dt.date.fromisoformat, default=dt.date.today())
    args=parser.parse_args()
    if args.count < 1 or args.days < 1:
        parser.error('--count and --days must be positive')
    sites=load_sites()
    added_sites=0
    for sid,name,archetype,stream in DEMO_SITES:
        if sid not in sites:
            save_site(dict(site_id=sid,site_name=name,site_type=archetype,bin_type=stream,
                           bin_configuration='Demo collection bin',gps=None,is_demo=True),creating=True)
            added_sites+=1
    sites=load_sites()
    existing=set()
    if AUDITS_PATH.exists():
        for line in AUDITS_PATH.read_text().splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict):
                    existing.add(row.get('bag_id'))
            except ValueError:
                continue
    added=0
    for record in generate(sites,args.count,args.days,args.end_date,args.seed):
        assert abs(sum(c['corrected_pct'] for c in record['categories'])-100)<.001
        if record['bag_id'] not in existing:
            save_audit(record)
            added+=1
    print(f'Added {added} mock audits and {added_sites} demo sites. Existing records preserved.')
    print(f'Dates: {args.end_date-dt.timedelta(days=args.days-1)} through {args.end_date}. Sites: {len(sites)}.')
    print("Dashboard: enable 'Include labeled mock audits'. Hazard results remain unavailable.")


if __name__=='__main__':
    main()
