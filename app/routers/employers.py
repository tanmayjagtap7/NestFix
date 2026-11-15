from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Employee, EmployeeSelection, Employer, HousingOption
from app.schemas import (
    EmployerCreate,
    EmployerOut,
    EmployerUpdate,
    EmployeeOut,
    SelectionsSummary,
    SelectionSummaryItem,
    UploadResult,
)
from app.services.geo import apply_workplace
from app.services.ingest import IngestError, parse_csv, upsert_employees

router = APIRouter()


def _employee_out(employee: Employee, options_count: int = 0) -> EmployeeOut:
    selection = employee.selection
    selected_option = selection.housing_option if selection else None
    payload = EmployeeOut.model_validate(employee).model_dump()
    payload["options_count"] = options_count
    payload["selected_option_id"] = selection.housing_option_id if selection else None
    payload["selected_address"] = selected_option.address if selected_option else None
    return EmployeeOut(**payload)


def _option_counts(db: Session, employer_id: int) -> Dict[int, int]:
    rows = (
        db.query(HousingOption.employee_id, func.count(HousingOption.id))
        .join(Employee, Employee.id == HousingOption.employee_id)
        .filter(Employee.employer_id == employer_id)
        .group_by(HousingOption.employee_id)
        .all()
    )
    return {employee_id: count for employee_id, count in rows}


@router.post("", response_model=EmployerOut)
def create_employer(body: EmployerCreate, db: Session = Depends(get_db)) -> Employer:
    if "@" not in body.contact_email:
        raise HTTPException(status_code=400, detail="contact_email needs to be an email address.")
    employer = Employer(company_name=body.company_name.strip(), contact_email=body.contact_email.strip())
    apply_workplace(employer, body.work_location)
    db.add(employer)
    db.commit()
    db.refresh(employer)
    return employer


@router.get("", response_model=List[EmployerOut])
def list_employers(db: Session = Depends(get_db)) -> List[Employer]:
    return db.query(Employer).order_by(Employer.id).all()


@router.post("/upload-employees", response_model=UploadResult)
async def upload_employees(request: Request, db: Session = Depends(get_db)) -> UploadResult:
    content_type = request.headers.get("content-type", "")
    defaults: Dict[str, Any] = {}
    try:
        if "application/json" in content_type:
            payload = await request.json()
            employer_id = int(payload.get("employer_id") or 0)
            rows = payload.get("employees") or []
            if not isinstance(rows, list) or not rows:
                raise IngestError("Send a non-empty employees list.")
            defaults = {
                "contribution_type": payload.get("contribution_type"),
                "contribution_amount": payload.get("contribution_amount"),
                "contribution_duration_months": payload.get("contribution_duration_months"),
            }
            normalized_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    raise IngestError("Each employee must be an object.")
                normalized_rows.append(row)
            rows = normalized_rows
        else:
            form = await request.form()
            employer_id = int(form.get("employer_id") or 0)
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                raise IngestError("Attach a CSV file in the file field.")
            raw = await upload.read()
            rows = parse_csv(raw)
            defaults = {
                "contribution_type": form.get("contribution_type") or None,
                "contribution_amount": form.get("contribution_amount") or None,
                "contribution_duration_months": form.get("contribution_duration_months") or None,
            }
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="employer_id must be an integer.") from exc

    employer = db.get(Employer, employer_id)
    if employer is None:
        raise HTTPException(status_code=404, detail="Employer not found.")
    try:
        created, updated, employees = upsert_employees(db, employer, rows, defaults)
    except IngestError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    counts = _option_counts(db, employer.id)
    return UploadResult(
        employer_id=employer.id,
        created=created,
        updated=updated,
        employees=[_employee_out(employee, counts.get(employee.id, 0)) for employee in employees],
    )


@router.patch("/{employer_id}", response_model=EmployerOut)
def update_employer(employer_id: int, body: EmployerUpdate, db: Session = Depends(get_db)) -> Employer:
    employer = db.get(Employer, employer_id)
    if employer is None:
        raise HTTPException(status_code=404, detail="Employer not found.")
    apply_workplace(employer, body.work_location)
    db.add(employer)
    db.commit()
    db.refresh(employer)
    return employer


@router.get("/{employer_id}", response_model=EmployerOut)
def get_employer(employer_id: int, db: Session = Depends(get_db)) -> Employer:
    employer = db.get(Employer, employer_id)
    if employer is None:
        raise HTTPException(status_code=404, detail="Employer not found.")
    return employer


@router.get("/{employer_id}/employees", response_model=List[EmployeeOut])
def list_employees(employer_id: int, db: Session = Depends(get_db)) -> List[EmployeeOut]:
    employer = db.get(Employer, employer_id)
    if employer is None:
        raise HTTPException(status_code=404, detail="Employer not found.")
    employees = (
        db.query(Employee)
        .options(joinedload(Employee.selection).joinedload(EmployeeSelection.housing_option))
        .filter(Employee.employer_id == employer_id)
        .order_by(Employee.id)
        .all()
    )
    counts = _option_counts(db, employer_id)
    return [_employee_out(employee, counts.get(employee.id, 0)) for employee in employees]


@router.get("/{employer_id}/selections-summary", response_model=SelectionsSummary)
def selections_summary(employer_id: int, db: Session = Depends(get_db)) -> SelectionsSummary:
    employer = db.get(Employer, employer_id)
    if employer is None:
        raise HTTPException(status_code=404, detail="Employer not found.")
    employees = (
        db.query(Employee)
        .options(joinedload(Employee.selection).joinedload(EmployeeSelection.housing_option))
        .filter(Employee.employer_id == employer_id)
        .order_by(Employee.full_name)
        .all()
    )
    counts = _option_counts(db, employer_id)
    items: List[SelectionSummaryItem] = []
    selected = 0
    ready = 0
    for employee in employees:
        if counts.get(employee.id, 0):
            ready += 1
        selection = employee.selection
        option: Optional[HousingOption] = selection.housing_option if selection else None
        if selection and option:
            selected += 1
            cover = None
            if option.price is not None and option.net_price is not None:
                cover = round(option.price - option.net_price, 2)
            items.append(
                SelectionSummaryItem(
                    employee_id=employee.id,
                    employee_id_external=employee.employee_id_external,
                    full_name=employee.full_name,
                    email=employee.email,
                    preferred_city=employee.preferred_city,
                    contribution_label=employee.contribution_label,
                    housing_option_id=option.id,
                    address=option.address,
                    sticker_price=option.price,
                    net_price=option.net_price,
                    employer_monthly_cover=cover,
                    selected_at=selection.selected_at,
                    employee_notes=selection.employee_notes,
                    status="selected",
                )
            )
        else:
            items.append(
                SelectionSummaryItem(
                    employee_id=employee.id,
                    employee_id_external=employee.employee_id_external,
                    full_name=employee.full_name,
                    email=employee.email,
                    preferred_city=employee.preferred_city,
                    contribution_label=employee.contribution_label,
                    status="waiting",
                )
            )
    return SelectionsSummary(
        employer=EmployerOut.model_validate(employer),
        total_employees=len(employees),
        selections_count=selected,
        pending_count=len(employees) - selected,
        options_ready_count=ready,
        selections=items,
    )
