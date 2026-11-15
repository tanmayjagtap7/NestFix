from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import AnalysisLog, Employee, EmployeeSelection, HousingOption
from app.schemas import (
    AffordabilityIn,
    AffordabilityOut,
    AnalysisLogOut,
    EmployeeOut,
    EmployeeUpdate,
    HousingOptionOut,
    OptionsResponse,
    RankedOption,
    SelectIn,
    SelectionOut,
)
from app.services.affordability import monthly_gross, rule_of_thumb_budget
from app.services.geo import distance_miles
from app.services.lookup import resolve_employee
from app.services.matching_service import rank_with_calculator

router = APIRouter()


def _miles_from_work(option: HousingOption):
    employer = option.employee.employer if option.employee is not None else None
    data = option.listing_data or {}
    if employer is None:
        return None
    return distance_miles(
        employer.work_latitude,
        employer.work_longitude,
        data.get("latitude"),
        data.get("longitude"),
    )


def _option_out(option: HousingOption) -> HousingOptionOut:
    payload = HousingOptionOut.model_validate(option).model_dump()
    if option.price is not None and option.net_price is not None:
        payload["employer_monthly_cover"] = round(option.price - option.net_price, 2)
    elif option.listing_data and option.listing_data.get("employer_monthly_cover") is not None:
        payload["employer_monthly_cover"] = option.listing_data.get("employer_monthly_cover")
    miles = _miles_from_work(option)
    if miles is not None:
        listing = dict(payload.get("listing_data") or {})
        listing["miles_from_work"] = miles
        payload["listing_data"] = listing
    return HousingOptionOut(**payload)


def _employee_out(employee) -> EmployeeOut:
    selection = employee.selection
    option = selection.housing_option if selection else None
    payload = EmployeeOut.model_validate(employee).model_dump()
    payload["options_count"] = len(employee.housing_options) if employee.housing_options is not None else 0
    payload["selected_option_id"] = selection.housing_option_id if selection else None
    payload["selected_address"] = option.address if option else None
    employer = employee.employer
    if employer is not None:
        payload["employer_name"] = employer.company_name
        payload["work_location"] = employer.work_location
    return EmployeeOut(**payload)


def _options_response(employee) -> OptionsResponse:
    options = sorted(
        employee.housing_options,
        key=lambda option: (
            _miles_from_work(option) if _miles_from_work(option) is not None and _miles_from_work(option) <= 80 else 10**6,
            -int((option.gemini_analysis or {}).get("score") or 0),
        ),
    )
    analysis = options[0].gemini_analysis if options else {}
    return OptionsResponse(
        employee=_employee_out(employee),
        monthly_gross=round(monthly_gross(employee.annual_salary), 2),
        housing_budget=round(rule_of_thumb_budget(employee.annual_salary), 2),
        contribution_label=employee.contribution_label,
        selected_option_id=employee.selection.housing_option_id if employee.selection else None,
        analysis_source=(analysis or {}).get("source"),
        gemini_error=(analysis or {}).get("gemini_error"),
        data_note=(options[0].amenities_data or {}).get("summary") if options else None,
        options=[_option_out(option) for option in options],
    )


@router.get("", response_model=List[EmployeeOut])
def list_all_employees(db: Session = Depends(get_db)) -> List[EmployeeOut]:
    employees = db.scalars(
        select(Employee)
        .options(
            joinedload(Employee.selection).joinedload(EmployeeSelection.housing_option),
            joinedload(Employee.housing_options),
        )
        .order_by(Employee.id)
    ).unique().all()
    return [_employee_out(employee) for employee in employees]


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: str, db: Session = Depends(get_db)) -> EmployeeOut:
    employee = _load(db, employee_id)
    return _employee_out(employee)


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: str, body: EmployeeUpdate, db: Session = Depends(get_db)) -> EmployeeOut:
    employee = _load(db, employee_id)
    changes = body.model_dump(exclude_unset=True)
    if "contribution_type" in changes and changes["contribution_type"] not in {
        "monthly_subsidy",
        "one_time_assistance",
        "percent_of_rent",
        None,
    }:
        raise HTTPException(status_code=400, detail="Choose a monthly amount, one-time help, or a percent of rent.")
    if "other_notes" in changes:
        changes["other_notes"] = (changes["other_notes"] or "").strip() or None
    if "preferred_city" in changes and changes["preferred_city"] is not None:
        city = changes["preferred_city"].strip()
        if not city:
            raise HTTPException(status_code=400, detail="City is required.")
        changes["preferred_city"] = city
    for key, value in changes.items():
        setattr(employee, key, value)
    db.commit()
    fresh = _load(db, str(employee.id))
    return _employee_out(fresh)


@router.get("/{employee_id}/options", response_model=OptionsResponse)
def get_options(employee_id: str, db: Session = Depends(get_db)) -> OptionsResponse:
    employee = _load(db, employee_id)
    return _options_response(employee)


@router.post("/{employee_id}/select-option", response_model=SelectionOut)
def select_option(employee_id: str, body: SelectIn, db: Session = Depends(get_db)) -> EmployeeSelection:
    employee = _load(db, employee_id)
    option = db.get(HousingOption, body.housing_option_id)
    if option is None or option.employee_id != employee.id:
        raise HTTPException(status_code=404, detail="That housing option is not on this employee's list.")
    selection = employee.selection
    if selection is None:
        selection = EmployeeSelection(
            employee_id=employee.id,
            housing_option_id=option.id,
            employee_notes=(body.employee_notes or "").strip() or None,
        )
        db.add(selection)
    else:
        selection.housing_option_id = option.id
        selection.employee_notes = (body.employee_notes or "").strip() or None
        selection.selected_at = datetime.utcnow()
    db.commit()
    db.refresh(selection)
    return selection


@router.post("/{employee_id}/affordability-calc", response_model=AffordabilityOut)
def affordability_calc(employee_id: str, body: AffordabilityIn, db: Session = Depends(get_db)) -> AffordabilityOut:
    employee = _load(db, employee_id)
    try:
        result = rank_with_calculator(db, employee, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["options"] = [RankedOption(**row) for row in result["options"]]
    return AffordabilityOut(**result)


@router.get("/{employee_id}/logs", response_model=List[AnalysisLogOut])
def employee_logs(employee_id: str, db: Session = Depends(get_db)) -> List[AnalysisLog]:
    employee = _load(db, employee_id)
    return (
        db.query(AnalysisLog)
        .filter(AnalysisLog.employee_id == employee.id)
        .order_by(AnalysisLog.id.desc())
        .limit(40)
        .all()
    )


def _load(db: Session, employee_id: str) -> Employee:
    found = resolve_employee(db, employee_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    return db.scalars(
        select(Employee)
        .options(
            joinedload(Employee.employer),
            joinedload(Employee.selection).joinedload(EmployeeSelection.housing_option),
            joinedload(Employee.housing_options),
        )
        .where(Employee.id == found.id)
    ).unique().one()
