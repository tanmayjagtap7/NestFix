"""Live housing and neighborhood data from Bright Data.

Search order:
1. SERP API when BRIGHT_DATA_SERP_ZONE (or a discovered serp zone) is available.
2. Web Unlocker enrichment when an unlocker zone is available.
3. Otherwise the Zillow search dataset plus Google Maps place searches,
   which this project's key can call without a SERP zone.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, quote_plus, urlencode

import httpx

logger = logging.getLogger("nestfix.bright_data")

HOUSING_DOMAINS = (
    "zillow.com",
    "apartments.com",
    "realtor.com",
    "redfin.com",
    "rent.com",
    "zumper.com",
    "hotpads.com",
    "trulia.com",
    "apartmentlist.com",
    "craigslist.org",
)


class BrightDataError(Exception):
    pass


class BrightDataService:
    BASE = "https://api.brightdata.com"

    def __init__(self) -> None:
        self.api_key = os.getenv("BRIGHT_DATA_API_KEY", "").strip()
        self.serp_zone = os.getenv("BRIGHT_DATA_SERP_ZONE", "").strip() or None
        self.unlocker_zone = os.getenv("BRIGHT_DATA_UNLOCKER_ZONE", "").strip() or None
        self.zillow_search_dataset = os.getenv(
            "BRIGHT_DATA_ZILLOW_SEARCH_DATASET", "gd_m71oxpvxwr113ehqg"
        )
        self.zillow_listings_dataset = os.getenv(
            "BRIGHT_DATA_ZILLOW_LISTINGS_DATASET", "gd_lfqkr8wm13ixtbd8f5"
        )
        self.maps_dataset = os.getenv("BRIGHT_DATA_MAPS_DATASET", "gd_m8ebnr0q2qlklc02fz")
        self._zones_resolved = False

    def search_housing_and_amenities(
        self,
        city: str,
        bedrooms: int,
        max_price: float,
    ) -> Dict[str, Any]:
        self._resolve_zones()
        note_parts: List[str] = []
        listings: List[Dict[str, Any]] = []
        used_serp = False

        if self.serp_zone:
            try:
                listings = self._search_serp(city, bedrooms, max_price)
                used_serp = True
                note_parts.append(f"SERP zone {self.serp_zone}")
                if self.unlocker_zone and listings:
                    self._enrich_with_unlocker(listings)
                    note_parts.append(f"Web Unlocker zone {self.unlocker_zone}")
            except BrightDataError as exc:
                logger.warning("SERP search failed, falling back to datasets: %s", exc)
                note_parts.append(f"SERP unavailable ({exc})")
                listings = []

        amenity_jobs: Dict[str, str] = {}
        if not listings:
            housing_snapshot = self._trigger_zillow_search(city, bedrooms, max_price)
            amenity_jobs = {}
            records = self._wait_snapshot(housing_snapshot, timeout=70, required=False)
            listings = [item for item in (self._normalize_listing(rec, city) for rec in records) if item]
            if not listings:
                logger.info("Zillow search returned %s usable rows; trying listing discovery", len(listings))
                try:
                    discovered = self._discover_zillow_listings(city, bedrooms)
                    extra = [item for item in (self._normalize_listing(rec, city) for rec in discovered) if item]
                    listings = self._merge_listings(listings, extra)
                    note_parts.append("Zillow listing discovery")
                except BrightDataError as exc:
                    logger.warning("Zillow discovery fallback failed: %s", exc)
                    note_parts.append(f"Zillow discovery skipped ({exc})")
            note_parts.append("Bright Data Zillow dataset")
        else:
            amenity_jobs = self._trigger_amenity_searches(city)

        amenities = self._collect_amenities(city, listings, amenity_jobs)
        if amenities.get("place_count"):
            note_parts.append("Bright Data Google Maps dataset")
        elif self.serp_zone:
            note_parts.append("amenity snippets from SERP")

        return {
            "listings": listings,
            "amenities": amenities,
            "note": "Live data via " + ", ".join(note_parts) if note_parts else "Bright Data",
            "used_serp": used_serp,
        }

    def integration_snapshot(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "detail": "BRIGHT_DATA_API_KEY is not set."}
        try:
            self._resolve_zones()
            mode = "serp" if self.serp_zone else "zillow_dataset"
            detail = (
                f"SERP zone '{self.serp_zone}' is configured."
                if self.serp_zone
                else "No SERP or Web Unlocker zone on this account. Live listings use the Zillow and Google Maps datasets."
            )
            if self.unlocker_zone:
                detail += f" Web Unlocker zone '{self.unlocker_zone}' is available."
            return {
                "ok": True,
                "mode": mode,
                "serp_zone": self.serp_zone,
                "unlocker_zone": self.unlocker_zone,
                "detail": detail,
            }
        except BrightDataError as exc:
            return {"ok": False, "detail": str(exc), "mode": None, "serp_zone": None, "unlocker_zone": None}

    def _resolve_zones(self) -> None:
        if self._zones_resolved:
            return
        self._zones_resolved = True
        if not self.api_key:
            return
        try:
            zones = self._request("GET", "/zone/get_active_zones", timeout=20)
        except BrightDataError as exc:
            logger.info("Could not list Bright Data zones: %s", exc)
            return
        if not isinstance(zones, list):
            return
        for zone in zones:
            if not isinstance(zone, dict):
                continue
            name = zone.get("name")
            ztype = str(zone.get("type") or "").lower()
            if not name:
                continue
            if not self.serp_zone and ztype == "serp":
                self.serp_zone = name
            if not self.unlocker_zone and ztype in {"unlocker", "unblocker", "web_unlocker"}:
                self.unlocker_zone = name

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise BrightDataError("BRIGHT_DATA_API_KEY is not set.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, timeout: float = 60, **kwargs: Any) -> Any:
        url = path if path.startswith("http") else f"{self.BASE}{path}"
        try:
            response = httpx.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise BrightDataError(f"Bright Data request failed: {exc}") from exc
        if response.status_code >= 400:
            raise BrightDataError(
                f"Bright Data returned {response.status_code}: {response.text[:400]}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw": response.text[:4000]}

    def _trigger(self, dataset_id: str, payload: Dict[str, Any], extra_params: Optional[Dict[str, Any]] = None) -> str:
        params: Dict[str, Any] = {"dataset_id": dataset_id, "include_errors": "true"}
        if extra_params:
            params.update(extra_params)
        data = self._request(
            "POST",
            "/datasets/v3/trigger",
            params=params,
            json=payload,
            timeout=45,
        )
        snapshot_id = data.get("snapshot_id") if isinstance(data, dict) else None
        if not snapshot_id:
            raise BrightDataError(f"Bright Data did not return a snapshot id: {str(data)[:300]}")
        return snapshot_id

    def _wait_snapshot(self, snapshot_id: str, timeout: int = 180, required: bool = False) -> List[Dict[str, Any]]:
        deadline = time.time() + timeout
        last_status = "running"
        while time.time() < deadline:
            try:
                progress = self._request("GET", f"/datasets/v3/progress/{snapshot_id}", timeout=30)
            except BrightDataError as exc:
                if required:
                    raise
                logger.warning("Progress check failed for %s: %s", snapshot_id, exc)
                return []
            last_status = str(progress.get("status") or "")
            if last_status == "ready":
                records = self._download_snapshot(snapshot_id)
                return records
            if last_status in {"failed", "error", "canceled", "cancelled"}:
                message = progress.get("error") or progress.get("message") or last_status
                if required:
                    raise BrightDataError(f"Bright Data snapshot failed: {message}")
                logger.warning("Snapshot %s failed: %s", snapshot_id, message)
                return []
            time.sleep(2)
        if required:
            raise BrightDataError(
                f"Bright Data is still collecting snapshot {snapshot_id} after {timeout}s. Try again in a minute."
            )
        logger.warning("Snapshot %s still %s after %ss", snapshot_id, last_status, timeout)
        return []

    def _download_snapshot(self, snapshot_id: str) -> List[Dict[str, Any]]:
        url = f"{self.BASE}/datasets/v3/snapshot/{snapshot_id}"
        try:
            response = httpx.get(
                url,
                headers=self._headers(),
                params={"format": "json"},
                timeout=90,
            )
        except httpx.HTTPError as exc:
            raise BrightDataError(f"Could not download Bright Data snapshot: {exc}") from exc
        if response.status_code == 202:
            return []
        if response.status_code >= 400:
            raise BrightDataError(
                f"Bright Data snapshot download returned {response.status_code}: {response.text[:300]}"
            )
        return self._parse_records(response.text)

    def _parse_records(self, text: str) -> List[Dict[str, Any]]:
        raw = (text or "").strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            rows = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    rows.append(parsed)
            return self._flatten(rows)
        if isinstance(data, list):
            return self._flatten([row for row in data if isinstance(row, dict)])
        if isinstance(data, dict):
            if data.get("status") == "running":
                return []
            for key in ("data", "results", "records", "organic"):
                inner = data.get(key)
                if isinstance(inner, list):
                    return self._flatten([row for row in inner if isinstance(row, dict)])
            return self._flatten([data])
        return []

    def _flatten(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flat: List[Dict[str, Any]] = []
        for rec in records:
            if rec.get("error") and not any(rec.get(k) for k in ("url", "address", "price", "name")):
                logger.info("Skipping Bright Data error row: %s", str(rec.get("error"))[:200])
                continue
            nested = None
            for key in ("homes", "listings", "results", "properties", "listResults", "organic"):
                inner = rec.get(key)
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    nested = inner
                    break
            if nested is not None:
                flat.extend(item for item in nested if isinstance(item, dict))
            else:
                flat.append(rec)
        return flat

    def _trigger_zillow_search(self, city: str, bedrooms: int, max_price: float) -> str:
        slug = city_slug(city)
        state = {
            "pagination": {},
            "isMapVisible": False,
            "filterState": {
                "sort": {"value": "priorityscore"},
                "fr": {"value": True},
                "fsba": {"value": False},
                "fsbo": {"value": False},
                "nc": {"value": False},
                "cmsn": {"value": False},
                "auc": {"value": False},
                "fore": {"value": False},
                "beds": {"min": max(0, int(bedrooms))},
                "price": {"max": max(800, int(max_price))},
                "mp": {"max": max(800, int(max_price))},
            },
            "isListVisible": True,
        }
        url = (
            f"https://www.zillow.com/{slug}/rentals/?searchQueryState="
            + quote(json.dumps(state, separators=(",", ":")))
        )
        logger.info("Triggering Zillow search for %s beds=%s cap=%s", city, bedrooms, max_price)
        return self._trigger(
            self.zillow_search_dataset,
            {"input": [{"url": url}]},
            {"limit_per_input": 3},
        )

    def _discover_zillow_listings(self, city: str, bedrooms: int) -> List[Dict[str, Any]]:
        home_type = "Apartments" if bedrooms <= 2 else ""
        payload = {
            "input": [
                {
                    "location": city,
                    "listingCategory": "House for rent",
                    "HomeType": home_type,
                }
            ]
        }
        snapshot = self._trigger(
            self.zillow_listings_dataset,
            payload,
            {
                "type": "discover_new",
                "discover_by": "input_filters",
                "limit_per_input": 4,
            },
        )
        return self._wait_snapshot(snapshot, timeout=35, required=False)

    def lookup_places(self, keyword: str, timeout: int = 12) -> List[Dict[str, str]]:
        cleaned = " ".join(str(keyword or "").split())[:140]
        key = cleaned.lower()
        if not cleaned or not self.api_key:
            return []
        cache = self._read_place_cache()
        entry = cache.get(key) if isinstance(cache.get(key), dict) else {}
        if entry.get("places"):
            return entry["places"]
        snapshot = entry.get("snapshot_id")
        if not snapshot:
            try:
                snapshot = self._trigger(
                    self.maps_dataset,
                    {"input": [{"keyword": cleaned, "country": "US"}]},
                    {"type": "discover_new", "discover_by": "location", "limit_per_input": 4},
                )
            except BrightDataError as exc:
                logger.warning("Place lookup did not start: %s", exc)
                return []
            cache[key] = {"snapshot_id": snapshot, "places": []}
            self._write_place_cache(cache)
        records = self._wait_snapshot(snapshot, timeout=timeout, required=False)
        places = self._normalize_places(records, "lookup")
        if places:
            cache[key] = {"snapshot_id": snapshot, "places": places}
            self._write_place_cache(cache)
        logger.info("Place lookup %s snapshot %s returned %s places", key, snapshot, len(places))
        return places

    def _place_cache_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "place_cache.json"

    def _read_place_cache(self) -> Dict[str, Any]:
        path = self._place_cache_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_place_cache(self, data: Dict[str, Any]) -> None:
        path = self._place_cache_path()
        path.write_text(json.dumps(data))

    def _trigger_amenity_searches(self, city: str) -> Dict[str, str]:
        queries = {
            "schools": f"elementary school in {city}",
            "parks": f"park in {city}",
            "hospitals": f"hospital in {city}",
            "transit": f"transit station in {city}",
        }
        jobs: Dict[str, str] = {}
        for kind, keyword in queries.items():
            try:
                jobs[kind] = self._trigger(
                    self.maps_dataset,
                    {"input": [{"keyword": keyword, "country": "US"}]},
                    {"type": "discover_new", "discover_by": "location", "limit_per_input": 4},
                )
            except BrightDataError as exc:
                logger.warning("Maps trigger for %s failed: %s", kind, exc)
        return jobs

    def _collect_amenities(
        self,
        city: str,
        listings: List[Dict[str, Any]],
        jobs: Dict[str, str],
    ) -> Dict[str, Any]:
        grouped: Dict[str, List[Dict[str, str]]] = {key: [] for key in ("schools", "parks", "hospitals", "transit")}
        sources: List[Dict[str, str]] = []
        deadline = time.time() + 20
        pending = dict(jobs)
        while pending and time.time() < deadline:
            for kind, snapshot_id in list(pending.items()):
                try:
                    progress = self._request("GET", f"/datasets/v3/progress/{snapshot_id}", timeout=20)
                except BrightDataError:
                    continue
                status = progress.get("status")
                if status == "ready":
                    records = self._download_snapshot(snapshot_id)
                    grouped[kind] = self._normalize_places(records, kind)
                    pending.pop(kind, None)
                elif status in {"failed", "error", "canceled", "cancelled"}:
                    pending.pop(kind, None)
            if pending:
                time.sleep(2)

        for listing in listings:
            for school in listing.get("schools") or []:
                if school not in grouped["schools"]:
                    grouped["schools"].append(school)

        place_count = sum(len(items) for items in grouped.values())
        summary = self._amenity_summary(city, grouped)
        for kind, places in grouped.items():
            for place in places[:3]:
                if place.get("url"):
                    sources.append({"title": place.get("name") or kind, "url": place["url"], "kind": kind})
        return {
            "scope": "city",
            "city": city,
            "summary": summary,
            "schools": grouped["schools"][:5],
            "parks": grouped["parks"][:4],
            "hospitals": grouped["hospitals"][:4],
            "transit": grouped["transit"][:4],
            "sources": sources[:8],
            "place_count": place_count,
            "provider": "bright_data_google_maps",
        }

    def _amenity_summary(self, city: str, grouped: Dict[str, List[Dict[str, str]]]) -> str:
        def names(kind: str) -> str:
            found = [place.get("name") for place in grouped.get(kind) or [] if place.get("name")]
            return ", ".join(found[:3])

        bits = []
        if names("schools"):
            bits.append(f"schools such as {names('schools')}")
        if names("parks"):
            bits.append(f"parks such as {names('parks')}")
        if names("hospitals"):
            bits.append(f"hospitals such as {names('hospitals')}")
        if names("transit"):
            bits.append(f"transit such as {names('transit')}")
        if not bits:
            return f"Nearby places in {city} were not listed on this pass."
        return f"Around {city}: " + "; ".join(bits) + "."

    def _normalize_places(self, records: List[Dict[str, Any]], kind: str) -> List[Dict[str, str]]:
        places = []
        seen = set()
        for rec in records:
            name = _first(rec, "name", "title", "place_name", "business_name")
            if not name or not isinstance(name, str):
                continue
            cleaned = name.strip()
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            url = _first(rec, "url", "link", "maps_url", "place_url")
            rating = _first(rec, "rating", "stars", "review_score")
            address = _format_address(_first(rec, "address", "full_address", "location"))
            lat = _first(rec, "lat", "latitude")
            lng = _first(rec, "lon", "lng", "longitude")
            note_bits = []
            if rating not in (None, ""):
                note_bits.append(f"rated {rating}")
            if address:
                note_bits.append(address)
            places.append(
                {
                    "name": cleaned,
                    "kind": kind,
                    "note": " · ".join(note_bits),
                    "url": url if isinstance(url, str) and url.startswith("http") else "",
                    "rating": rating if rating not in (None, "") else None,
                    "address": address or "",
                    "lat": lat,
                    "lng": lng,
                }
            )
            if len(places) >= 5:
                break
        return places

    def _search_serp(self, city: str, bedrooms: int, max_price: float) -> List[Dict[str, Any]]:
        query = (
            f"{bedrooms} bedroom apartment for rent in {city} "
            f"under ${int(max_price)} site:zillow.com OR site:apartments.com OR site:realtor.com"
        )
        search_url = "https://www.google.com/search?" + urlencode(
            {"q": query, "hl": "en", "gl": "us", "num": "10", "brd_json": "1"}
        )
        payload = self._request(
            "POST",
            "/request",
            json={
                "zone": self.serp_zone,
                "url": search_url,
                "format": "raw",
                "country": "us",
            },
            timeout=90,
        )
        parsed = _unwrap_serp(payload)
        organic = parsed.get("organic") if isinstance(parsed, dict) else None
        if not isinstance(organic, list):
            organic = []
        listings = []
        for item in organic:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_serp_item(item, city)
            if normalized:
                listings.append(normalized)
        amenity_query = f"elementary schools parks hospitals transit near {city}"
        amenity_url = "https://www.google.com/search?" + urlencode(
            {"q": amenity_query, "hl": "en", "gl": "us", "num": "8", "brd_json": "1"}
        )
        try:
            amenity_payload = self._request(
                "POST",
                "/request",
                json={"zone": self.serp_zone, "url": amenity_url, "format": "raw", "country": "us"},
                timeout=90,
            )
            amenity_parsed = _unwrap_serp(amenity_payload)
            self._serp_amenity_cache = amenity_parsed if isinstance(amenity_parsed, dict) else {}
        except BrightDataError as exc:
            logger.warning("Amenity SERP failed: %s", exc)
            self._serp_amenity_cache = {}
        if not listings:
            raise BrightDataError("SERP returned no housing results.")
        return listings

    def _normalize_serp_item(self, item: Dict[str, Any], city: str) -> Optional[Dict[str, Any]]:
        link = item.get("link") or item.get("url") or ""
        title = item.get("title") or ""
        snippet = item.get("description") or item.get("snippet") or ""
        text = f"{title} {snippet}"
        if link and not any(domain in link for domain in HOUSING_DOMAINS):
            if not re.search(r"rent|apartment|bedroom|condo|home", text, re.I):
                return None
        price = _price_from_text(text)
        beds = _beds_from_text(text)
        baths = _baths_from_text(text)
        return {
            "source_url": link,
            "address": _address_from_title(title) or title or "Listing from search",
            "price": price,
            "bedrooms": beds,
            "bathrooms": baths,
            "sqft": _sqft_from_text(text),
            "image_url": item.get("image") if isinstance(item.get("image"), str) and str(item.get("image")).startswith("http") else None,
            "description": snippet[:500],
            "home_type": None,
            "schools": [],
            "city": city,
            "provider": "bright_data_serp",
            "title": title,
        }

    def _enrich_with_unlocker(self, listings: List[Dict[str, Any]]) -> None:
        top = next((item for item in listings if item.get("source_url")), None)
        if not top:
            return
        try:
            unlocked = self._request(
                "POST",
                "/request",
                json={
                    "zone": self.unlocker_zone,
                    "url": top["source_url"],
                    "format": "raw",
                    "data_format": "markdown",
                    "country": "us",
                },
                timeout=50,
            )
        except BrightDataError as exc:
            logger.warning("Web Unlocker enrichment failed: %s", exc)
            return
        text = unlocked if isinstance(unlocked, str) else json.dumps(unlocked)[:4000]
        if isinstance(unlocked, dict):
            text = unlocked.get("body") or unlocked.get("raw") or text
        if isinstance(text, str) and text.strip():
            top["unlocked_excerpt"] = text.strip()[:2500]
            if top.get("price") is None:
                top["price"] = _price_from_text(top["unlocked_excerpt"])

    def _normalize_listing(self, rec: Dict[str, Any], city: str) -> Optional[Dict[str, Any]]:
        if not isinstance(rec, dict):
            return None
        address = _format_address(
            _first(rec, "address", "streetAddress", "full_address", "hdpData")
        )
        if address is None:
            address = _first(rec, "addressStreet", "street")
            if isinstance(address, str):
                locality = " ".join(
                    part
                    for part in [
                        str(_first(rec, "city", "addressCity") or ""),
                        str(_first(rec, "state", "addressState") or ""),
                        str(_first(rec, "zipcode", "zip", "addressZipcode") or ""),
                    ]
                    if part
                )
                address = ", ".join(part for part in [address, locality] if part)
        title = _first(rec, "statusText", "title", "name") or ""
        url = _first(rec, "url", "detailUrl", "hdpUrl", "link")
        if isinstance(url, str) and url.startswith("/"):
            url = "https://www.zillow.com" + url
        if isinstance(url, str) and (not address or not re.match(r"\d", str(address))):
            from_url = _address_from_zillow_url(url, city)
            if from_url:
                address = from_url
        price = _as_number(_first(rec, "price", "unformattedPrice", "rentZestimate", "rent_zestimate"))
        if price is not None and price > 20000:
            price = None
        beds = _as_number(_first(rec, "bedrooms", "beds", "beds_min"))
        if beds is None:
            beds = _beds_from_text(str(title) + " " + str(_first(rec, "description") or ""))
        baths = _as_number(_first(rec, "bathrooms", "baths"))
        sqft = _as_number(_first(rec, "livingArea", "living_area", "sqft", "area"))
        if not address and not url and price is None:
            return None
        description = _first(rec, "description", "overview") or ""
        if not isinstance(description, str):
            description = ""
        status = str(_first(rec, "homeStatus", "home_status") or "")
        if status and "RENT" not in status.upper() and "PENDING" not in status.upper():
            return None
        if price is None:
            price = _as_number(_first(rec, "base_rent"))
            if price is not None and price > 20000:
                price = None
        transit = []
        scores = rec.get("getting_around_scores") if isinstance(rec.get("getting_around_scores"), dict) else {}
        for key in ("walk_score", "transit_score", "bike_score"):
            if scores.get(key):
                transit.append(str(scores[key]))
        neighborhoods = []
        for neighborhood in rec.get("nearbyNeighborhoods") or []:
            if isinstance(neighborhood, dict) and neighborhood.get("name"):
                neighborhoods.append(str(neighborhood["name"]))
        return {
            "source_url": url if isinstance(url, str) else None,
            "address": address or str(title) or "Zillow rental",
            "price": price,
            "bedrooms": beds,
            "bathrooms": baths,
            "sqft": sqft if sqft and sqft > 50 else _as_number(rec.get("sqft")),
            "image_url": _image_url(rec),
            "description": description[:500],
            "home_type": _first(rec, "homeType", "home_type", "propertyType"),
            "schools": _schools(rec),
            "transit": transit,
            "neighborhoods": neighborhoods[:6],
            "city": _first(rec, "city") or city,
            "latitude": _as_number(_first(rec, "latitude", "lat")),
            "longitude": _as_number(_first(rec, "longitude", "lng", "lon")),
            "provider": "bright_data_zillow",
            "title": title if isinstance(title, str) else "",
        }

    def _merge_listings(self, primary: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        merged = []
        for item in primary + extra:
            key = (item.get("source_url") or item.get("address") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged


def city_slug(city: str) -> str:
    cleaned = city.lower().replace(",", " ")
    cleaned = re.sub(r"[^a-z0-9\s-]", "", cleaned)
    cleaned = re.sub(r"\s+", "-", cleaned.strip())
    return cleaned or "austin-tx"


def _first(rec: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in rec and rec[key] not in (None, "", [], {}):
            value = rec[key]
            if key == "hdpData" and isinstance(value, dict):
                info = value.get("homeInfo") if isinstance(value.get("homeInfo"), dict) else value
                return info
            return value
    return None


def _format_address(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        if any(k in value for k in ("streetAddress", "city", "zipcode")):
            street = value.get("streetAddress") or value.get("street") or ""
            city = value.get("city") or ""
            state = value.get("state") or ""
            zipcode = value.get("zipcode") or value.get("zip") or ""
            state_zip = f"{state} {zipcode}".strip()
            parts = [part for part in [street, city, state_zip] if part]
            return ", ".join(parts) or None
        info = value.get("homeInfo") if isinstance(value.get("homeInfo"), dict) else None
        if info:
            return _format_address(info.get("address") or info)
    return None


def _as_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return _as_number(value.get("value") or value.get("price") or value.get("amount"))
    if isinstance(value, str):
        match = re.search(r"\d[\d,]*\.?\d*", value.replace(",", ""))
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", ""))
        except ValueError:
            return None
    return None


def _price_from_text(text: str) -> Optional[float]:
    match = re.search(r"\$\s*([0-9]{1,2},?[0-9]{3})(?:\s*/\s*mo)?", text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    if value < 400 or value > 20000:
        return None
    return value


def _beds_from_text(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:bed|beds|bd|br|bedroom)", text, re.I)
    if not match:
        return None
    return float(match.group(1))


def _baths_from_text(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:ba|bath)", text, re.I)
    if not match:
        return None
    return float(match.group(1))


def _sqft_from_text(text: str) -> Optional[float]:
    match = re.search(r"([\d,]{3,6})\s*(?:sq\.?\s*ft|sqft)", text, re.I)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _address_from_zillow_url(url: str, city: str) -> Optional[str]:
    match = re.search(r"/homedetails/([^/]+)/", url or "")
    if not match:
        return None
    text = match.group(1).replace("-", " ")
    text = re.sub(r"\s+([A-Za-z]{2})\s+(\d{5})$", r", \1 \2", text)
    city_name = (city or "").split(",")[0].strip()
    if city_name:
        text = re.sub(rf"\s+({re.escape(city_name)}),", r", \1,", text, count=1)
    return text if re.match(r"\d", text) else None


def _address_from_title(title: str) -> Optional[str]:
    if not title:
        return None
    cleaned = re.sub(r"\s+\|\s+Zillow.*$", "", title, flags=re.I).strip()
    if re.search(r"\d", cleaned) and re.search(r"\b[A-Z]{2}\b|\d{5}", cleaned):
        return cleaned
    return None


def _image_url(rec: Dict[str, Any]) -> Optional[str]:
    for key in ("imgSrc", "image", "photo", "main_image", "primary_photo"):
        value = rec.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    photos = rec.get("photos") or rec.get("images") or []
    if isinstance(photos, list):
        for photo in photos:
            if isinstance(photo, str) and photo.startswith("http"):
                return photo
            if isinstance(photo, dict):
                url = photo.get("url") or photo.get("mixedSources")
                if isinstance(url, str) and url.startswith("http"):
                    return url
    return None


def _schools(rec: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = rec.get("schools") or rec.get("nearbySchools") or []
    if not isinstance(raw, list):
        return []
    schools = []
    for school in raw:
        if isinstance(school, str):
            schools.append({"name": school, "kind": "schools", "note": "", "url": ""})
            continue
        if not isinstance(school, dict):
            continue
        name = school.get("name") or school.get("school_name")
        if not name:
            continue
        bits = []
        if school.get("rating") not in (None, ""):
            bits.append(f"rating {school.get('rating')}")
        if school.get("distance") not in (None, ""):
            bits.append(f"{school.get('distance')} mi")
        grades = school.get("grades") or school.get("level") or school.get("type")
        if grades:
            bits.append(str(grades))
        link = school.get("link") or school.get("url") or ""
        schools.append(
            {
                "name": str(name),
                "kind": "schools",
                "note": " · ".join(bits),
                "url": link if isinstance(link, str) else "",
            }
        )
    return schools[:4]


def _unwrap_serp(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and "organic" in payload:
        return payload
    if isinstance(payload, dict):
        body = payload.get("body")
        if isinstance(body, dict):
            return body
        if isinstance(body, str):
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"html": body[:4000]}
        raw = payload.get("raw")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"html": raw[:4000]}
    return {}
