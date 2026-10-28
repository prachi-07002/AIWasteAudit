"""SQLAlchemy ORM models.

Site is a lookup table (seeded from configs/sites.yaml via
scripts/seed_sites.py). Audit is one photo/run. Detection is one item
found within an audit, so contaminant breakdowns can be queried/aggregated
directly in SQL rather than only from the computed JSON breakdown.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Site(Base):
    __tablename__ = "sites"

    site_id: Mapped[str] = mapped_column(String, primary_key=True)
    site_name: Mapped[str] = mapped_column(String, nullable=False)
    site_type: Mapped[str] = mapped_column(String, index=True)
    bin_type: Mapped[str] = mapped_column(String)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    audits: Mapped[list["Audit"]] = relationship(back_populates="site")


class Audit(Base):
    __tablename__ = "audits"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.site_id"), index=True)
    stream_type: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)
    image_path: Mapped[str] = mapped_column(String)

    contamination_pct: Mapped[float] = mapped_column(Float)
    hazard_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)  # human-in-the-loop QA flag

    site: Mapped["Site"] = relationship(back_populates="audits")
    detections: Mapped[list["DetectionRecord"]] = relationship(back_populates="audit")


class DetectionRecord(Base):
    """One classified item within an audit — kept as rows (not just JSON)
    so contaminant breakdowns can be aggregated directly in SQL, e.g.
    "most common contaminant class by site_type".
    """

    __tablename__ = "detections"

    detection_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.audit_id"), index=True)

    class_name: Mapped[str] = mapped_column(String, index=True)
    material_category: Mapped[str] = mapped_column(String)
    is_contaminant: Mapped[bool] = mapped_column(Boolean, index=True)
    hazard_flag: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[float] = mapped_column(Float)
    mask_area_px: Mapped[int] = mapped_column(Integer)
    pct_of_audit_area: Mapped[float] = mapped_column(Float)

    # human correction fields — populated if a reviewer overrides the model
    corrected_class_name: Mapped[str | None] = mapped_column(String, nullable=True)

    audit: Mapped["Audit"] = relationship(back_populates="detections")
