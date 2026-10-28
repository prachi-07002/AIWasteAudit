"""Load configs/sites.yaml into the sites table (upsert by site_id).

Usage:
    python scripts/seed_sites.py
"""
from waste_audit.db.models import Site
from waste_audit.db.session import get_session
from waste_audit.utils.config import load_sites

if __name__ == "__main__":
    sites = load_sites()
    session = get_session()

    for site_id, record in sites.items():
        existing = session.get(Site, site_id)
        gps = record.get("gps") or {}
        if existing:
            existing.site_name = record["site_name"]
            existing.site_type = record["site_type"]
            existing.bin_type = record["bin_type"]
        else:
            session.add(
                Site(
                    site_id=site_id,
                    site_name=record["site_name"],
                    site_type=record["site_type"],
                    bin_type=record["bin_type"],
                    gps_lat=gps.get("lat"),
                    gps_lon=gps.get("lon"),
                )
            )

    session.commit()
    print(f"Seeded {len(sites)} sites.")
