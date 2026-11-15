"""Follow-up answers about one home, using saved facts and a place lookup."""

import logging
import math
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import HousingOption, HousingQuestion
from app.services.affordability import employer_monthly_cover, money
from app.services.bright_data_service import BrightDataService
from app.services.gemini_service import GeminiError, GeminiService

logger = logging.getLogger("nestfix.questions")

PLACE_WORDS = (
    "school",
    "park",
    "hospital",
    "transit",
    "bus",
    "train",
    "grocery",
    "store",
    "shop",
    "restaurant",
    "gym",
    "commute",
    "nearby",
    "near ",
    "distance",
    "walk",
    "yard",
    "playground",
    "doctor",
    "pharmacy",
    "coffee",
    "library",
    "walmart",
    "target",
    "closest",
    "how far",
    "market",
)


def needs_place_lookup(question: str) -> bool:
    text = question.lower()
    return any(word in text for word in PLACE_WORDS)


def answer_about_option(db: Session, option: HousingOption, question: str) -> HousingQuestion:
    facts = _facts(option)
    places: List[Dict[str, Any]] = []
    looked_up = False
    if needs_place_lookup(question) and not _already_on_file(question, facts):
        looked_up = True
        keyword = _place_keyword(question, facts.get("city") or "")
        try:
            found = BrightDataService().lookup_places(keyword, timeout=50)
        except Exception:
            logger.exception("Place lookup failed")
            found = []
        annotated = [_with_distance(place, facts.get("latitude"), facts.get("longitude")) for place in found]
        places = [place for place in annotated if place.get("miles_away") is not None and place["miles_away"] <= 20]
        places.sort(key=lambda place: place["miles_away"])
        logger.info("Place lookup for option %s kept %s nearby places", option.id, len(places))
        if not found:
            answer = "I'm still gathering places near this home. Ask again in a minute and I'll include names and distances."
        elif not places:
            answer = "Nothing within 20 miles of this home came back for that."
        else:
            answer = _describe_places(places)
    else:
        answer = None
    if answer is None:
        try:
            answer = GeminiService().answer_home_question(facts, question.strip(), places)
        except GeminiError as exc:
            logger.warning("Home question fell back to saved facts: %s", exc)
            answer = _fallback_answer(facts, places)
    answer = _scrub(answer)
    row = HousingQuestion(housing_option_id=option.id, question=question.strip(), answer=answer)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _describe_places(places: List[Dict[str, Any]]) -> str:
    def one(place: Dict[str, Any], closest: bool) -> str:
        address = re.sub(r",?\s*United States$", "", str(place.get("address") or ""), flags=re.I).strip()
        sentence = f"{place.get('name')} is {place.get('miles_away')} miles away"
        if address:
            sentence += f" at {address}"
        rating = place.get("rating")
        if rating not in (None, "", 0, "0"):
            sentence += f", rated {rating}"
        if closest:
            sentence += ", and it is the closest"
        return sentence + "."

    if not places:
        return "Nothing within 20 miles of this home came back for that."
    lines = [one(place, index == 0) for index, place in enumerate(places[:4])]
    return " ".join(lines)


def _place_keyword(question: str, city: str) -> str:
    text = question.lower()
    subjects = (
        ("walmart", "Walmart"),
        ("target", "Target"),
        ("grocery", "grocery store"),
        ("supermarket", "grocery store"),
        ("park", "park"),
        ("school", "school"),
        ("hospital", "hospital"),
        ("transit", "transit"),
        ("store", "store"),
    )
    label = next((name for needle, name in subjects if needle in text), question.strip())
    return f"{label} in {city}".strip()


def _already_on_file(question: str, facts: Dict[str, Any]) -> bool:
    text = question.lower()
    for place in facts.get("saved_places") or []:
        name = str(place.get("name") or "").lower()
        if len(name) > 4 and name in text:
            return True
    return False


def _facts(option: HousingOption) -> Dict[str, Any]:
    employee = option.employee
    listing = option.listing_data or {}
    amenities = option.amenities_data or {}
    analysis = option.gemini_analysis or {}
    lat = _number(listing.get("latitude"))
    lng = _number(listing.get("longitude"))
    saved: List[Dict[str, Any]] = []
    for kind in ("schools", "hospitals", "transit", "parks"):
        for place in amenities.get(kind) or []:
            if isinstance(place, dict) and place.get("name"):
                saved.append(_with_distance({**place, "kind": kind}, lat, lng))
    saved.sort(key=lambda place: place.get("miles_away") if place.get("miles_away") is not None else 999)

    return {
        "employee_name": employee.full_name,
        "city": listing.get("city") or employee.preferred_city,
        "family_size": employee.family_size,
        "children": employee.num_children,
        "household_notes": employee.other_notes,
        "annual_salary": employee.annual_salary,
        "employer_help": employee.contribution_label,
        "address": option.address,
        "latitude": lat,
        "longitude": lng,
        "listed_rent": option.price,
        "employer_pays_monthly": employer_monthly_cover(
            option.price,
            employee.contribution_type,
            employee.contribution_amount,
            employee.contribution_duration_months,
        ),
        "employee_pays_monthly": option.net_price,
        "bedrooms": option.bedrooms,
        "bathrooms": option.bathrooms,
        "sqft": option.sqft,
        "home_type": listing.get("home_type"),
        "saved_places": saved,
        "pros": analysis.get("pros") or [],
        "cons": analysis.get("cons") or [],
    }


def _with_distance(place: Dict[str, Any], lat: Optional[float], lng: Optional[float]) -> Dict[str, Any]:
    place_lat = _number(place.get("lat"))
    place_lng = _number(place.get("lng"))
    if place_lat is None or place_lng is None:
        coords = _coords_from_url(str(place.get("url") or ""))
        if coords:
            place_lat, place_lng = coords
    miles = _miles(lat, lng, place_lat, place_lng) if None not in (lat, lng, place_lat, place_lng) else None
    rating = place.get("rating")
    if rating in (None, "", 0, "0"):
        match = re.search(r"rat(?:ed|ing)\s+([0-9]+(?:\.[0-9]+)?)", str(place.get("note") or ""), re.I)
        rating = float(match.group(1)) if match and float(match.group(1)) > 0 else None
    address = place.get("address") or ""
    if not address:
        for part in str(place.get("note") or "").split("·"):
            part = part.strip()
            if re.search(r"\d", part) and not re.search(r"rat(?:ed|ing)|\bmi\b", part, re.I):
                address = re.sub(r",?\s*United States$", "", part, flags=re.I)
                break
    return {
        "name": place.get("name"),
        "kind": place.get("kind"),
        "rating": rating,
        "address": address,
        "miles_away": round(miles, 1) if miles is not None else None,
    }


def _coords_from_url(url: str) -> Optional[tuple]:
    match = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", url)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    def rad(value: float) -> float:
        return value * math.pi / 180

    d_lat = rad(lat2 - lat1)
    d_lng = rad(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(d_lng / 2) ** 2
    return 3958.8 * 2 * math.asin(min(1, math.sqrt(a)))


def _number(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fallback_answer(facts: Dict[str, Any], places: List[Dict[str, Any]]) -> str:
    bits = [
        f"{facts.get('address')} is listed at {money(facts.get('listed_rent'))}.",
        f"After employer help, the monthly cost is {money(facts.get('employee_pays_monthly'))}.",
    ]
    saved = facts.get("saved_places") or []
    if saved:
        nearest = saved[0]
        away = f", {nearest['miles_away']} miles away" if nearest.get("miles_away") is not None else ""
        bits.append(f"Closest place on file is {nearest.get('name')}{away}.")
    fresh = [place.get("name") for place in places if place.get("name")]
    if fresh:
        bits.append("A fresh look nearby turned up " + ", ".join(fresh[:3]) + ".")
    else:
        bits.append("Nothing else on file answers that more specifically.")
    return " ".join(bits)


def _scrub(answer: str) -> str:
    text = re.sub(r"\bbright data\b", "the search", answer, flags=re.IGNORECASE)
    text = re.sub(r"\bgemini\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip()
