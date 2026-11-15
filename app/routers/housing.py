import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import HousingOption, HousingQuestion
from app.routers.employees import _load, _options_response, _option_out
from app.schemas import GenerateResponse, HousingOptionOut, QuestionIn, QuestionOut
from app.services.bright_data_service import BrightDataError
from app.services.matching_service import generate_options_for_employee
from app.services.photos import property_photos
from app.services.questions import answer_about_option

router = APIRouter()
logger = logging.getLogger("nestfix.housing")


@router.post("/generate-options/{employee_id}", response_model=GenerateResponse)
def generate_options(employee_id: str, db: Session = Depends(get_db)) -> GenerateResponse:
    employee = _load(db, employee_id)
    try:
        result = generate_options_for_employee(db, employee)
    except BrightDataError as exc:
        logger.warning("Search failed: %s", exc)
        raise HTTPException(status_code=502, detail="No rentals came back for that city. Try again.") from exc
    except Exception:
        logger.exception("Option generation failed")
        raise HTTPException(status_code=500, detail="The search did not finish. Try again.")

    fresh = _load(db, str(employee.id))
    payload = _options_response(fresh).model_dump()
    payload["options_created"] = len(result["options"])
    payload["bright_data_note"] = result["bright_data_note"]
    payload["analysis_source"] = result["analysis_source"]
    payload["gemini_error"] = result["gemini_error"]
    return GenerateResponse(**payload)


@router.get("/options/{option_id}/photos")
def list_photos(option_id: int, db: Session = Depends(get_db)) -> dict:
    option = _option_or_404(db, option_id)
    try:
        return property_photos(db, option)
    except Exception:
        logger.exception("Photo lookup failed")
        return {"photos": [], "pending": False}


@router.get("/options/{option_id}/questions", response_model=List[QuestionOut])
def list_questions(option_id: int, db: Session = Depends(get_db)) -> List[QuestionOut]:
    _option_or_404(db, option_id)
    rows = (
        db.query(HousingQuestion)
        .filter(HousingQuestion.housing_option_id == option_id)
        .order_by(HousingQuestion.created_at.asc(), HousingQuestion.id.asc())
        .all()
    )
    return [QuestionOut.model_validate(row) for row in rows]


@router.post("/options/{option_id}/ask", response_model=QuestionOut)
def ask_about_option(option_id: int, payload: QuestionIn, db: Session = Depends(get_db)) -> QuestionOut:
    option = _option_or_404(db, option_id)
    try:
        row = answer_about_option(db, option, payload.question)
    except Exception:
        logger.exception("Home question failed")
        raise HTTPException(status_code=500, detail="Could not answer that. Try again.")
    return QuestionOut.model_validate(row)


def _option_or_404(db: Session, option_id: int) -> HousingOption:
    option = db.get(HousingOption, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Housing option not found.")
    return option


@router.get("/options/{option_id}", response_model=HousingOptionOut)
def get_option(option_id: int, db: Session = Depends(get_db)) -> HousingOptionOut:
    option = db.get(HousingOption, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Housing option not found.")
    return _option_out(option)
