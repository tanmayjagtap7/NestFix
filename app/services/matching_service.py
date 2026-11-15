"""Turn Bright Data listings into stored housing options for one employee."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import AnalysisLog, Employee, EmployeeSelection, HousingOption, HousingQuestion
from app.services.affordability import (
    contribution_label,
    employer_monthly_cover,
    money,
    monthly_gross,
    net_monthly_price,
    rule_of_thumb_budget,
    sticker_search_cap,
)
from app.services.bright_data_service import BrightDataError, BrightDataService
from app.services.geo import distance_miles
from app.services.gemini_service import GeminiError, GeminiService

logger = logging.getLogger("nestfix.matching")

bright_data = BrightDataService()
gemini = GeminiService()


def generate_options_for_employee(db: Session, employee: Employee) -> Dict[str, Any]:
    bedrooms = employee.min_bedrooms or 1
    cap = sticker_search_cap(employee)
    budget = rule_of_thumb_budget(employee.annual_salary)
    _log(
        db,
        employee.id,
        "bright_data",
        "search",
        "started",
        f"city={employee.preferred_city}; bedrooms={bedrooms}; sticker_cap={cap:.0f}",
        "",
        "Collecting live listings and nearby places.",
    )
    cached = _listings_for_city(db, employee.preferred_city)
    try:
        if len(cached["listings"]) >= 3:
            found = cached
            logger.info("Reusing %s saved listings for %s", len(cached["listings"]), employee.preferred_city)
        else:
            found = bright_data.search_housing_and_amenities(employee.preferred_city, bedrooms, cap)
    except BrightDataError as exc:
        _log(db, employee.id, "bright_data", "search", "error", "", "", str(exc))
        raise

    listings = found.get("listings") or []
    amenities = found.get("amenities") or {}
    note = found.get("note") or "Bright Data"
    _log(
        db,
        employee.id,
        "bright_data",
        "search",
        "ok",
        f"city={employee.preferred_city}",
        f"{len(listings)} listings; places={amenities.get('place_count', 0)}",
        note,
    )
    if not listings:
        raise BrightDataError(f"No rentals came back for {employee.preferred_city}. Try again.")

    office = employee.employer
    for item in listings:
        item["miles_from_work"] = distance_miles(
            office.work_latitude if office is not None else None,
            office.work_longitude if office is not None else None,
            item.get("latitude"),
            item.get("longitude"),
        )
    chosen = _choose(listings, employee, budget)[:5]
    for item in chosen:
        price = item.get("price")
        cover = employer_monthly_cover(
            price,
            employee.contribution_type,
            employee.contribution_amount,
            employee.contribution_duration_months,
        )
        item["employer_monthly_cover"] = round(cover, 2) if price is not None else None
        item["net_price"] = net_monthly_price(
            price,
            employee.contribution_type,
            employee.contribution_amount,
            employee.contribution_duration_months,
        )

    context = employee_context(employee, budget)
    gemini_error = None
    analyses: Dict[int, Dict[str, Any]] = {}
    amenity_summary = amenities.get("summary") or ""
    source = "nestfix_rules"
    try:
        reviewed = gemini.analyze(context, chosen, amenities)
        for row in reviewed.get("options") or []:
            if isinstance(row, dict) and isinstance(row.get("source_index"), int):
                analyses[row["source_index"]] = _gemini_row(row)
        if reviewed.get("amenities_summary"):
            amenity_summary = reviewed["amenities_summary"]
        if analyses:
            source = "gemini"
        _log(
            db,
            employee.id,
            "gemini",
            "analyze",
            "ok",
            employee.full_name,
            f"{len(analyses)} explanations",
            "Gemini ranked the Bright Data listings for this employee.",
        )
    except GeminiError as exc:
        gemini_error = str(exc)
        _log(db, employee.id, "gemini", "analyze", "error", employee.full_name, "", gemini_error)
        logger.warning("Gemini analysis unavailable: %s", gemini_error)

    shared_amenities = dict(amenities)
    shared_amenities["summary"] = amenity_summary
    shared_amenities["summary_source"] = source if source == "gemini" else "bright_data"

    saved: List[HousingOption] = []
    old_ids = [
        row[0]
        for row in db.query(HousingOption.id).filter(HousingOption.employee_id == employee.id).all()
    ]
    if old_ids:
        db.query(HousingQuestion).filter(HousingQuestion.housing_option_id.in_(old_ids)).delete(
            synchronize_session=False
        )
        db.query(EmployeeSelection).filter(EmployeeSelection.housing_option_id.in_(old_ids)).delete(
            synchronize_session=False
        )
    db.query(EmployeeSelection).filter(EmployeeSelection.employee_id == employee.id).delete()
    db.query(HousingOption).filter(HousingOption.employee_id == employee.id).delete()

    scored_rows = []
    for index, item in enumerate(chosen):
        analysis = analyses.get(index) or _local_analysis(employee, item, shared_amenities, budget)
        if gemini_error and analysis.get("source") != "gemini":
            analysis["gemini_error"] = gemini_error
        analysis["score"] = _clamp_score(analysis.get("score"))
        scored_rows.append((analysis["score"], index, item, analysis))

    scored_rows.sort(key=lambda row: row[0], reverse=True)
    for score, _index, item, analysis in scored_rows:
        option = HousingOption(
            employee_id=employee.id,
            source_url=item.get("source_url"),
            address=(item.get("address") or "Rental listing")[:400],
            price=item.get("price"),
            bedrooms=item.get("bedrooms"),
            bathrooms=item.get("bathrooms"),
            sqft=item.get("sqft"),
            net_price=item.get("net_price"),
            listing_data={
                "provider": item.get("provider"),
                "home_type": item.get("home_type"),
                "image_url": item.get("image_url"),
                "image_urls": item.get("image_urls") or [],
                "description": item.get("description"),
                "title": item.get("title"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "employer_monthly_cover": item.get("employer_monthly_cover"),
                "search_city": employee.preferred_city,
                "sticker_cap": cap,
                "transit": item.get("transit") or [],
                "neighborhoods": item.get("neighborhoods") or [],
                "miles_from_work": item.get("miles_from_work"),
            },
            amenities_data=_amenities_for_listing(item, shared_amenities),
            gemini_analysis=analysis,
        )
        db.add(option)
        saved.append(option)
    db.commit()
    for option in saved:
        db.refresh(option)
    return {
        "options": saved,
        "analysis_source": source,
        "gemini_error": gemini_error,
        "bright_data_note": note,
    }


def _listings_for_city(db: Session, city: str) -> Dict[str, Any]:
    wanted = (city or "").strip().casefold()
    if not wanted:
        return {"listings": [], "amenities": {}, "note": "Saved listings", "used_serp": False}
    rows = db.query(HousingOption).join(Employee).all()
    listings: List[Dict[str, Any]] = []
    seen = set()
    amenities: Dict[str, Any] = {}
    for option in rows:
        person = option.employee
        if (person.preferred_city or "").strip().casefold() != wanted:
            continue
        key = (option.source_url or option.address or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        data = option.listing_data or {}
        places = option.amenities_data or {}
        if not amenities and places:
            amenities = {
                "summary": places.get("summary") or "",
                "schools": places.get("schools") or [],
                "parks": places.get("parks") or [],
                "hospitals": places.get("hospitals") or [],
                "transit": places.get("transit") or [],
                "city": places.get("city") or city,
                "place_count": sum(len(places.get(kind) or []) for kind in ("schools", "parks", "hospitals", "transit")),
                "scope": "city",
            }
        listings.append(
            {
                "address": option.address,
                "source_url": option.source_url,
                "price": option.price,
                "bedrooms": option.bedrooms,
                "bathrooms": option.bathrooms,
                "sqft": option.sqft,
                "home_type": data.get("home_type"),
                "image_url": data.get("image_url"),
                "image_urls": data.get("image_urls") or [],
                "description": data.get("description"),
                "title": data.get("title"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "transit": data.get("transit") or [],
                "neighborhoods": data.get("neighborhoods") or [],
                "schools": places.get("schools") or [],
                "provider": data.get("provider"),
                "city": data.get("search_city") or person.preferred_city,
            }
        )
    return {"listings": listings, "amenities": amenities, "note": "Saved listings", "used_serp": False}


def rank_with_calculator(db: Session, employee: Employee, payload: Dict[str, Any]) -> Dict[str, Any]:
    expenses = float(payload["other_monthly_expenses"])
    savings = float(payload["desired_savings"])
    ratio = float(payload.get("take_home_ratio") or 0.75)
    gross = monthly_gross(employee.annual_salary)
    take_home = gross * ratio
    housing_budget = round(take_home - expenses - savings, 2)
    options = (
        db.query(HousingOption)
        .filter(HousingOption.employee_id == employee.id)
        .all()
    )
    if not options:
        raise ValueError("Generate housing options before running the calculator.")

    original = sorted(
        options,
        key=lambda option: _clamp_score((option.gemini_analysis or {}).get("score")),
        reverse=True,
    )
    original_rank = {option.id: index + 1 for index, option in enumerate(original)}
    need = employee.min_bedrooms or 1

    ranked_rows = []
    for option in options:
        net = option.net_price
        fits = net is not None and net <= housing_budget
        cushion = None if net is None else round(housing_budget - net, 2)
        ratio_to_gross = None
        if net is not None and gross:
            ratio_to_gross = round(net / gross, 3)
        if net is None:
            note = "Rent was not listed, so this home cannot be checked against the calculator."
        elif fits:
            note = f"${cushion:,.0f} left after rent, other bills, and savings."
        else:
            over = abs(cushion or 0)
            note = f"${over:,.0f} over the calculator budget."
        beds = option.bedrooms or 0
        ranked_rows.append(
            {
                "option": option,
                "fits_budget": bool(fits),
                "monthly_cushion": cushion,
                "rent_to_income_ratio": ratio_to_gross,
                "note": note,
                "sort": (
                    0 if fits else 1,
                    0 if beds >= need else 1,
                    -(cushion if cushion is not None else -10**9),
                ),
            }
        )
    ranked_rows.sort(key=lambda row: row["sort"])

    brief = []
    results = []
    for index, row in enumerate(ranked_rows):
        option = row["option"]
        results.append(
            {
                "housing_option_id": option.id,
                "address": option.address,
                "net_price": option.net_price,
                "sticker_price": option.price,
                "bedrooms": option.bedrooms,
                "score": (option.gemini_analysis or {}).get("score"),
                "fits_budget": row["fits_budget"],
                "monthly_cushion": row["monthly_cushion"],
                "rent_to_income_ratio": row["rent_to_income_ratio"],
                "rank": index + 1,
                "original_rank": original_rank.get(option.id, index + 1),
                "note": row["note"],
            }
        )
        brief.append(
            {
                "rank": index + 1,
                "address": option.address,
                "net_price": option.net_price,
                "fits_budget": row["fits_budget"],
            }
        )

    calc = {
        "monthly_gross": round(gross, 2),
        "estimated_take_home": round(take_home, 2),
        "other_monthly_expenses": expenses,
        "desired_savings": savings,
        "housing_budget": housing_budget,
    }
    narrative_source = "nestfix_rules"
    try:
        narrative = gemini.affordability_narrative(employee_context(employee, rule_of_thumb_budget(employee.annual_salary)), calc, brief)
        narrative_source = "gemini"
        _log(db, employee.id, "gemini", "affordability", "ok", employee.full_name, narrative[:240], "")
    except GeminiError as exc:
        fits_count = sum(1 for row in results if row["fits_budget"])
        narrative = (
            f"{employee.full_name} grosses about ${gross:,.0f}/month. "
            f"At {int(ratio * 100)}% take-home, that is ${take_home:,.0f} before other bills. "
            f"After ${expenses:,.0f} in other expenses and ${savings:,.0f} set aside, "
            f"${housing_budget:,.0f} remains for housing in {employee.preferred_city}. "
            f"{fits_count} of {len(results)} matched homes fit that number for a household of {employee.family_size}."
        )
        _log(db, employee.id, "gemini", "affordability", "error", employee.full_name, "", str(exc))

    return {**calc, "narrative": narrative, "narrative_source": narrative_source, "options": results}


def employee_context(employee: Employee, budget: float) -> Dict[str, Any]:
    return {
        "full_name": employee.full_name,
        "family_size": employee.family_size,
        "num_children": employee.num_children,
        "annual_salary": employee.annual_salary,
        "monthly_gross": round(monthly_gross(employee.annual_salary), 2),
        "housing_budget_30_percent": round(budget, 2),
        "preferred_city": employee.preferred_city,
        "max_commute_minutes": employee.max_commute_minutes,
        "min_bedrooms": employee.min_bedrooms,
        "other_notes": employee.other_notes,
        "contribution": contribution_label(employee),
        "employer": employee.employer.company_name if employee.employer else None,
        "workplace": employee.employer.work_location if employee.employer else None,
    }


def _choose(listings: List[Dict[str, Any]], employee: Employee, budget: float) -> List[Dict[str, Any]]:
    need = employee.min_bedrooms or 1
    unique = []
    seen = set()
    for item in listings:
        key = (item.get("source_url") or item.get("address") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)

    def sort_key(item: Dict[str, Any]):
        beds = item.get("bedrooms") or 0
        price = item.get("price")
        net = net_monthly_price(
            price,
            employee.contribution_type,
            employee.contribution_amount,
            employee.contribution_duration_months,
        )
        bed_rank = 0 if beds >= need else 1
        miles = item.get("miles_from_work")
        close = miles if isinstance(miles, (int, float)) and miles <= 80 else 10**6
        if net is None:
            return (bed_rank, 2, close, 10**9, 0)
        over = 0 if net <= budget * 1.08 else 1
        return (bed_rank, over, close, abs(net - budget), -beds)

    unique.sort(key=sort_key)
    by_address: Dict[str, List[Dict[str, Any]]] = {}
    for item in unique:
        street = (item.get("address") or "unknown").split(",")[0].strip().lower()
        by_address.setdefault(street, []).append(item)
    if len(by_address) >= 3:
        picked = []
        for group in by_address.values():
            group.sort(key=sort_key)
            picked.append(group[0])
        picked.sort(key=sort_key)
        return picked
    meeting = [item for item in unique if (item.get("bedrooms") or 0) >= need]
    return meeting if len(meeting) >= 3 else unique


def _amenities_for_listing(item: Dict[str, Any], shared: Dict[str, Any]) -> Dict[str, Any]:
    schools = item.get("schools") or shared.get("schools") or []
    parks = shared.get("parks") or []
    hospitals = shared.get("hospitals") or []
    transit_places = list(shared.get("transit") or [])
    for note in item.get("transit") or []:
        transit_places.append({"name": note, "kind": "transit", "note": "", "url": ""})
    neighborhoods = item.get("neighborhoods") or []
    bits = []
    school_names = [school.get("name") for school in schools if school.get("name")]
    park_names = [park.get("name") for park in parks if park.get("name")]
    hospital_names = [place.get("name") for place in hospitals if place.get("name")]
    transit_names = [place.get("name") for place in transit_places if place.get("name")]
    if school_names:
        bits.append("Schools include " + ", ".join(school_names[:3]))
    if transit_names:
        bits.append("Getting around: " + "; ".join(transit_names[:3]))
    if neighborhoods:
        bits.append("Nearby neighborhoods include " + ", ".join(neighborhoods[:4]))
    if park_names:
        bits.append("Parks include " + ", ".join(park_names[:3]))
    if hospital_names:
        bits.append("Hospitals include " + ", ".join(hospital_names[:2]))
    summary = ". ".join(bits) + "." if bits else (shared.get("summary") or "")
    if shared.get("summary_source") == "gemini" and shared.get("summary"):
        summary = shared["summary"]
    return {
        "scope": "listing" if item.get("schools") or item.get("transit") else shared.get("scope") or "city",
        "city": item.get("city") or shared.get("city"),
        "summary": summary,
        "schools": schools[:5],
        "parks": parks[:4],
        "hospitals": hospitals[:4],
        "transit": transit_places[:5],
        "neighborhoods": neighborhoods[:6],
        "sources": shared.get("sources") or [],
        "provider": item.get("provider") or shared.get("provider"),
        "summary_source": shared.get("summary_source") or "bright_data",
    }


def _gemini_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source": "gemini",
        "score": row.get("score"),
        "pros": _string_list(row.get("pros")),
        "cons": _string_list(row.get("cons")),
        "why_fits": str(row.get("why_fits") or "").strip(),
        "affordability_summary": str(row.get("affordability_summary") or "").strip(),
        "ranking_rationale": str(row.get("ranking_rationale") or "").strip(),
    }


def _local_analysis(
    employee: Employee,
    listing: Dict[str, Any],
    amenities: Dict[str, Any],
    budget: float,
) -> Dict[str, Any]:
    beds = listing.get("bedrooms")
    need = employee.min_bedrooms or 1
    net = listing.get("net_price")
    price = listing.get("price")
    cover = listing.get("employer_monthly_cover") or 0
    city = employee.preferred_city
    pros: List[str] = []
    cons: List[str] = []

    if beds is not None and beds >= need:
        pros.append(f"{_num(beds)} bedrooms meets the {need}-bedroom need for a household of {employee.family_size}.")
    elif beds is not None:
        cons.append(f"{_num(beds)} bedrooms is short of the {need} requested.")
    else:
        cons.append("Bedroom count was not listed.")

    if net is not None and net <= budget:
        pros.append(
            f"Net rent of ${net:,.0f} sits inside the ${budget:,.0f} guideline, 30% of gross pay."
        )
    elif net is not None:
        cons.append(f"Net rent of ${net:,.0f} is above the ${budget:,.0f} guideline.")
    else:
        cons.append("No rent was listed, so the employer contribution could not be applied.")

    if cover:
        pros.append(f"{contribution_label(employee)} covers about ${cover:,.0f} this month.")

    schools = amenities.get("schools") or []
    if employee.num_children and schools:
        pros.append(f"Around {city}, {schools[0].get('name')} is among the nearby schools.")
    parks = amenities.get("parks") or []
    if parks:
        pros.append(f"Nearby park: {parks[0].get('name')}.")
    miles = listing.get("miles_from_work")
    if isinstance(miles, (int, float)) and miles <= 150:
        sentence = f"About {miles:g} miles from the workplace."
        if miles <= 12:
            pros.append(sentence)
        else:
            cons.append(sentence)
    elif employee.max_commute_minutes:
        cons.append(f"Commute was not measured. The request was to stay under {employee.max_commute_minutes} minutes.")

    child_word = "child" if (employee.num_children or 0) == 1 else "children"
    why = (
        f"{employee.full_name} needs housing in {city} for {employee.family_size} people, "
        f"including {employee.num_children} {child_word}, on ${employee.annual_salary:,.0f} a year. "
        f"{listing.get('address')} is listed at {money(price)}. "
        f"{contribution_label(employee)} brings the monthly cost to {money(net)}."
    )
    if employee.other_notes:
        why += f" Employer note on file: {employee.other_notes.strip()}"

    within = net is not None and net <= budget
    affordability = (
        f"Gross monthly pay is about ${monthly_gross(employee.annual_salary):,.0f}. "
        f"The 30% housing guideline is ${budget:,.0f}. "
        f"After the employer contribution, this home is {'inside' if within else 'outside'} that guideline."
    )
    score = 68
    if beds is not None and beds >= need:
        score += 12
    else:
        score -= 18
    if net is not None and budget:
        ratio = net / budget
        if ratio <= 1:
            score += 12
        elif ratio <= 1.2:
            score -= 8
        else:
            score -= 18
    if employee.num_children and schools:
        score += 4
    return {
        "source": "nestfix_rules",
        "score": score,
        "pros": pros[:4],
        "cons": cons[:3],
        "why_fits": why,
        "affordability_summary": affordability,
        "ranking_rationale": "Ranked from bedroom fit and net rent against 30% of gross pay.",
    }


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:5]


def _clamp_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 50
    return max(1, min(99, score))


def _num(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _log(
    db: Session,
    employee_id: Optional[int],
    service: str,
    action: str,
    status: str,
    request_summary: str,
    response_summary: str,
    detail: str,
) -> None:
    db.add(
        AnalysisLog(
            employee_id=employee_id,
            service=service,
            action=action,
            status=status,
            request_summary=(request_summary or "")[:1000],
            response_summary=(response_summary or "")[:2000],
            detail=(detail or "")[:2000],
        )
    )
    db.commit()
