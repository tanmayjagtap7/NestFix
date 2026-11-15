"""Workplace address lookup and distance to a home."""

import logging
import math
from typing import Optional, Tuple

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Employer

logger = logging.getLogger("nestfix.geo")

DEFAULT_WORKPLACE = "2100 E St Elmo Rd, Austin, TX 78744"


def ensure_employer_columns() -> None:
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(employers)")).fetchall()
        if not rows:
            return
        names = {row[1] for row in rows}
        if "work_location" not in names:
            conn.execute(text("ALTER TABLE employers ADD COLUMN work_location VARCHAR(300)"))
        if "work_latitude" not in names:
            conn.execute(text("ALTER TABLE employers ADD COLUMN work_latitude FLOAT"))
        if "work_longitude" not in names:
            conn.execute(text("ALTER TABLE employers ADD COLUMN work_longitude FLOAT"))


def geocode(query: str) -> Optional[Tuple[float, float]]:
    cleaned = " ".join(str(query or "").split())
    if len(cleaned) < 3:
        return None
    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": cleaned, "format": "json", "limit": 1},
            headers={"User-Agent": "NestFix/1.0 (local housing demo)"},
            timeout=12,
        )
        response.raise_for_status()
        rows = response.json()
    except Exception:
        logger.exception("Workplace lookup failed")
        return None
    if not isinstance(rows, list) or not rows:
        return None
    try:
        return float(rows[0]["lat"]), float(rows[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def apply_workplace(employer: Employer, location: str) -> None:
    cleaned = " ".join(str(location or "").split())
    employer.work_location = cleaned or None
    point = geocode(cleaned) if cleaned else None
    employer.work_latitude = point[0] if point else None
    employer.work_longitude = point[1] if point else None


def place_default_workplace(db: Session) -> None:
    employer = db.query(Employer).filter(Employer.company_name == "Harborlight Logistics").first()
    if employer is None or (employer.work_location or "").strip():
        return
    apply_workplace(employer, DEFAULT_WORKPLACE)
    db.commit()


def distance_miles(lat1, lng1, lat2, lng2) -> Optional[float]:
    try:
        points = [float(lat1), float(lng1), float(lat2), float(lng2)]
    except (TypeError, ValueError):
        return None
    if any(point != point for point in points):
        return None
    lat1, lng1, lat2, lng2 = points
    radius = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    arc = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lng / 2) ** 2
    miles = 2 * radius * math.asin(math.sqrt(arc))
    return round(miles, 1)
