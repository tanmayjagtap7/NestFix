from typing import Optional

from sqlalchemy.orm import Session

from app.models import Employee


def resolve_employee(db: Session, key: str) -> Optional[Employee]:
    text = str(key).strip()
    if text.isdigit():
        employee = db.get(Employee, int(text))
        if employee is not None:
            return employee
    return db.query(Employee).filter(Employee.employee_id_external == text).one_or_none()
