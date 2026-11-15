import csv
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Employee, Employer
from app.services.affordability import CONTRIBUTION_TYPES, default_bedrooms


class IngestError(Exception):
    pass


HEADER_ALIASES = {
    "employee_id": "employee_id",
    "employeeid": "employee_id",
    "full_name": "full_name",
    "name": "full_name",
    "email": "email",
    "annual_salary": "annual_salary",
    "salary": "annual_salary",
    "family_size": "family_size",
    "num_children": "num_children",
    "children": "num_children",
    "preferred_city": "preferred_city",
    "work_location": "preferred_city",
    "city": "preferred_city",
    "max_commute_minutes": "max_commute_minutes",
    "min_bedrooms": "min_bedrooms",
    "other_notes": "other_notes",
    "notes": "other_notes",
    "contribution_type": "contribution_type",
    "contribution_amount": "contribution_amount",
    "contribution_duration_months": "contribution_duration_months",
}


def parse_csv(raw: bytes) -> List[Dict[str, Any]]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestError("The CSV needs a header row.")
    rows = []
    for line_number, raw_row in enumerate(reader, start=2):
        mapped: Dict[str, Any] = {}
        for key, value in raw_row.items():
            if key is None:
                continue
            normalized = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
            field = HEADER_ALIASES.get(normalized)
            if field:
                mapped[field] = (value or "").strip()
        if not any(mapped.values()):
            continue
        mapped["_line"] = line_number
        rows.append(mapped)
    if not rows:
        raise IngestError("The CSV has headers but no employee rows.")
    return rows


def upsert_employees(
    db: Session,
    employer: Employer,
    rows: List[Dict[str, Any]],
    defaults: Optional[Dict[str, Any]] = None,
) -> Tuple[int, int, List[Employee]]:
    defaults = defaults or {}
    created = 0
    updated = 0
    saved: List[Employee] = []
    for row in rows:
        data = _normalize_row(row, defaults)
        existing = (
            db.query(Employee)
            .filter(
                Employee.employer_id == employer.id,
                Employee.employee_id_external == data["employee_id_external"],
            )
            .one_or_none()
        )
        if existing is None:
            employee = Employee(employer_id=employer.id, **data)
            db.add(employee)
            created += 1
            saved.append(employee)
        else:
            for key, value in data.items():
                setattr(existing, key, value)
            updated += 1
            saved.append(existing)
    db.commit()
    for employee in saved:
        db.refresh(employee)
    return created, updated, saved


def _normalize_row(row: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    line = row.get("_line")
    prefix = f"Row {line}: " if line else ""

    external = str(row.get("employee_id") or "").strip()
    name = str(row.get("full_name") or "").strip()
    email = str(row.get("email") or "").strip()
    city = str(row.get("preferred_city") or row.get("work_location") or "").strip()
    if not external or not name or not email or not city:
        raise IngestError(prefix + "employee_id, full_name, email, and preferred_city are required.")
    if "@" not in email:
        raise IngestError(prefix + f"{email} is not an email address.")

    salary = _required_number(row.get("annual_salary"), prefix + "annual_salary")
    family_size = int(_required_number(row.get("family_size"), prefix + "family_size"))
    if salary <= 0 or family_size < 1:
        raise IngestError(prefix + "salary and family size must be positive.")

    children_raw = row.get("num_children")
    num_children = int(_optional_number(children_raw) or 0)
    if num_children < 0:
        raise IngestError(prefix + "num_children cannot be negative.")

    contribution_type = str(row.get("contribution_type") or defaults.get("contribution_type") or "").strip()
    if contribution_type not in CONTRIBUTION_TYPES:
        allowed = ", ".join(CONTRIBUTION_TYPES)
        raise IngestError(prefix + f"contribution_type must be one of {allowed}.")

    amount_value = row.get("contribution_amount")
    if amount_value in (None, ""):
        amount_value = defaults.get("contribution_amount")
    amount = _required_number(amount_value, prefix + "contribution_amount")
    if amount < 0:
        raise IngestError(prefix + "contribution_amount cannot be negative.")
    if contribution_type == "percent_of_rent" and amount > 100:
        raise IngestError(prefix + "percent_of_rent cannot be above 100.")

    duration_raw = row.get("contribution_duration_months")
    if duration_raw in (None, ""):
        duration_raw = defaults.get("contribution_duration_months")
    duration = _optional_number(duration_raw)
    duration_int = int(duration) if duration is not None else None

    bedrooms_raw = row.get("min_bedrooms")
    bedrooms = _optional_number(bedrooms_raw)
    min_bedrooms = int(bedrooms) if bedrooms is not None else default_bedrooms(family_size)

    commute = _optional_number(row.get("max_commute_minutes"))
    notes = str(row.get("other_notes") or "").strip() or None

    return {
        "employee_id_external": external,
        "full_name": name,
        "email": email,
        "annual_salary": float(salary),
        "family_size": family_size,
        "num_children": num_children,
        "preferred_city": city,
        "max_commute_minutes": int(commute) if commute is not None else None,
        "min_bedrooms": min_bedrooms,
        "contribution_type": contribution_type,
        "contribution_amount": float(amount),
        "contribution_duration_months": duration_int,
        "other_notes": notes,
    }


def _required_number(value: Any, label: str) -> float:
    number = _optional_number(value)
    if number is None:
        raise IngestError(f"{label} is required and must be a number.")
    return number


def _optional_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        return None
    return float(cleaned)
