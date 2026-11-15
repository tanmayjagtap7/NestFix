"""Gemini explanations for a specific employee's housing options."""

import json
import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger("nestfix.gemini")


class GeminiError(Exception):
    pass


class GeminiService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"

    def integration_snapshot(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "detail": "GEMINI_API_KEY is not set.", "model": self.model_name}
        try:
            self.ping()
            return {"ok": True, "detail": f"Gemini model {self.model_name} accepted the key.", "model": self.model_name}
        except GeminiError as exc:
            return {"ok": False, "detail": str(exc), "model": self.model_name}

    def ping(self) -> None:
        import httpx

        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY is not set.")
        try:
            response = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"pageSize": 1},
                headers={"x-goog-api-key": self.api_key},
                timeout=8,
            )
        except httpx.HTTPError as exc:
            raise GeminiError(f"Could not reach Gemini: {exc}") from exc
        if response.status_code >= 400:
            raise self._wrap(GeminiError(response.text[:300]))

    def analyze(self, employee: Dict[str, Any], listings: List[Dict[str, Any]], amenities: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._analysis_prompt(employee, listings, amenities)
        parsed = self._generate_json(prompt)
        options = parsed.get("options") if isinstance(parsed, dict) else None
        if not isinstance(options, list):
            raise GeminiError("Gemini did not return a JSON options list.")
        summary = ""
        amenity_block = parsed.get("amenities") if isinstance(parsed, dict) else None
        if isinstance(amenity_block, dict):
            summary = str(amenity_block.get("summary") or "")
        return {"options": options, "amenities_summary": summary}

    def answer_home_question(self, facts: Dict[str, Any], question: str, places: List[Dict[str, Any]]) -> str:
        prompt = (
            "Answer one follow-up question about a rental home for this employee.\n"
            "Use the saved places and the fresh nearby places. Each place may include miles_away, rating, and address.\n"
            "When miles_away is present, state that distance. Name the closest matching place first.\n"
            "Do not invent a place that is not in the facts. If nothing matches, say so in one sentence.\n"
            "Do not mention Gemini, Bright Data, scores, or APIs.\n"
            'Return JSON {"answer": "2 to 5 plain sentences"}.\n\n'
            f"Question: {question}\n"
            f"Facts: {json.dumps(facts)}\n"
            f"Fresh nearby places: {json.dumps(places)}\n"
        )
        parsed = self._generate_json(prompt)
        answer = parsed.get("answer") if isinstance(parsed, dict) else None
        if not answer:
            raise GeminiError("No answer was returned.")
        return str(answer).strip()

    def affordability_narrative(self, employee: Dict[str, Any], calc: Dict[str, Any], ranked: List[Dict[str, Any]]) -> str:
        prompt = (
            "Write a plain-language affordability note for this employee. "
            "Use only the numbers provided. Return JSON {\"narrative\": \"2-4 sentences\"}.\n\n"
            f"Employee: {json.dumps(employee)}\n"
            f"Calculator: {json.dumps(calc)}\n"
            f"Ranked options: {json.dumps(ranked)}\n"
            "Name the person, city, family size, and whether the top option fits the calculator budget."
        )
        parsed = self._generate_json(prompt)
        narrative = parsed.get("narrative") if isinstance(parsed, dict) else None
        if not narrative:
            raise GeminiError("Gemini did not return an affordability narrative.")
        return str(narrative).strip()

    def _analysis_prompt(self, employee: Dict[str, Any], listings: List[Dict[str, Any]], amenities: Dict[str, Any]) -> str:
        compact_listings = []
        for index, listing in enumerate(listings):
            compact_listings.append(
                {
                    "source_index": index,
                    "address": listing.get("address"),
                    "url": listing.get("source_url"),
                    "listed_rent": listing.get("price"),
                    "net_rent_after_employer": listing.get("net_price"),
                    "employer_monthly_cover": listing.get("employer_monthly_cover"),
                    "bedrooms": listing.get("bedrooms"),
                    "bathrooms": listing.get("bathrooms"),
                    "sqft": listing.get("sqft"),
                    "description": listing.get("description"),
                    "schools_on_listing": [school.get("name") for school in listing.get("schools") or []],
                    "getting_around": listing.get("transit"),
                    "neighborhoods": listing.get("neighborhoods"),
                }
            )
        compact_amenities = {
            "summary": amenities.get("summary"),
            "schools": [place.get("name") for place in amenities.get("schools") or []],
            "parks": [place.get("name") for place in amenities.get("parks") or []],
            "hospitals": [place.get("name") for place in amenities.get("hospitals") or []],
            "transit": [place.get("name") for place in amenities.get("transit") or []],
        }
        return (
            "You are Nestfix, advising one employee on real rental listings their employer collected.\n"
            "Use only the employee facts and listing facts below. Do not invent prices, addresses, or amenities.\n"
            "Explain the fit for THIS person: name, salary, family size, children, city, commute, and contribution.\n"
            "Return JSON with this shape:\n"
            "{\n"
            '  "amenities": {"summary": "2-3 sentences about the neighborhood for this household"},\n'
            '  "options": [{\n'
            '    "source_index": 0,\n'
            '    "score": 0,\n'
            '    "pros": ["specific"],\n'
            '    "cons": ["specific"],\n'
            '    "why_fits": "2-3 sentences",\n'
            '    "affordability_summary": "plain language using salary and employer contribution",\n'
            '    "ranking_rationale": "one sentence"\n'
            "  }]\n"
            "}\n"
            "score is 1-99. Rank better budget and bedroom fits higher. Include every source_index you were given.\n\n"
            f"Employee:\n{json.dumps(employee, indent=2)}\n\n"
            f"Listings from Bright Data:\n{json.dumps(compact_listings, indent=2)}\n\n"
            f"Nearby places from Bright Data:\n{json.dumps(compact_amenities, indent=2)}\n"
        )

    def _generate_json(self, prompt: str) -> Dict[str, Any]:
        import httpx

        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY is not set.")

        models = []
        for name in (self.model_name, "gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"):
            if name and name not in models:
                models.append(name)

        last_error = "Gemini did not return a response."
        with httpx.Client(timeout=25) as client:
            for name in models:
                for attempt in range(2):
                    try:
                        response = client.post(
                            f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent",
                            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                            json={
                                "contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {
                                    "temperature": 0.2,
                                    "responseMimeType": "application/json",
                                    "maxOutputTokens": 4096,
                                },
                            },
                        )
                    except httpx.HTTPError as exc:
                        last_error = f"Could not reach Gemini: {exc}"
                        logger.warning("Gemini model %s failed: %s", name, last_error[:300])
                        break
                    if response.status_code in (429, 503):
                        last_error = f"{name} is busy. Google reported high demand."
                        logger.warning("Gemini model %s busy (attempt %s)", name, attempt + 1)
                        break
                    if response.status_code >= 400:
                        wrapped = self._wrap(GeminiError(response.text[:500]))
                        if "rejected GEMINI_API_KEY" in str(wrapped):
                            raise wrapped
                        last_error = str(wrapped)
                        logger.warning("Gemini model %s failed: %s", name, last_error[:300])
                        break
                    text = _response_text(response.json())
                    if not text.strip():
                        last_error = f"{name} returned an empty response."
                        break
                    logger.info("Gemini model %s wrote the explanation", name)
                    return _parse_json(text)
        raise GeminiError(last_error[:500])

    def _wrap(self, exc: Exception) -> GeminiError:
        message = str(exc)
        if "API key not valid" in message or "API_KEY_INVALID" in message or "invalid api key" in message.lower():
            return GeminiError(
                "Google rejected GEMINI_API_KEY. Paste the key from Google AI Studio into .env. New keys start with AQ. Older keys start with AIza. Then generate the options again."
            )
        if "high demand" in message.lower() or "UNAVAILABLE" in message:
            return GeminiError("Gemini is busy right now. Try Refresh live homes again in a minute.")
        if "no longer available" in message.lower():
            return GeminiError("That Gemini model is not available for this key. Nestfix will try another model.")
        return GeminiError(message[:500])


def _response_text(payload: Dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    return "".join(str(part.get("text") or "") for part in parts)


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            raise GeminiError(f"Gemini returned non-JSON text: {cleaned[:180]}") from exc
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as inner:
            raise GeminiError(f"Gemini returned non-JSON text: {cleaned[:180]}") from inner
    if not isinstance(parsed, dict):
        raise GeminiError("Gemini JSON was not an object.")
    return parsed
