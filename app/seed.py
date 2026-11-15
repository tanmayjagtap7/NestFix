from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Employer
from app.services.ingest import parse_csv, upsert_employees

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "sample_employees.csv"


def seed_if_empty(db: Session) -> None:
    if db.query(Employer).first() is not None:
        return
    employer = Employer(company_name="Harborlight Logistics", contact_email="people@harborlight.example")
    db.add(employer)
    db.commit()
    db.refresh(employer)
    if not SAMPLE_CSV.exists():
        return
    rows = parse_csv(SAMPLE_CSV.read_bytes())
    upsert_employees(db, employer, rows)
