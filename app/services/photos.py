"""Photos of the home from its listing."""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm.attributes import flag_modified

from app.models import HousingOption
from app.services.bright_data_service import BrightDataService

logger = logging.getLogger("nestfix.photos")


def property_photos(db, option: HousingOption) -> Dict[str, Any]:
    data = dict(option.listing_data or {})
    stored = _stored_photos(data)
    if stored:
        return {"photos": stored, "pending": False}
    url = option.source_url or ""
    if "zillow.com" not in url:
        return {"photos": [], "pending": False}
    found = BrightDataService().listing_images(url)
    photos = _as_photos(found.get("photos") or [])
    if photos:
        data["image_urls"] = [item["url"] for item in photos]
        data["image_url"] = photos[0]["url"]
        option.listing_data = data
        flag_modified(option, "listing_data")
        db.add(option)
        db.commit()
    return {"photos": photos, "pending": bool(found.get("pending")) and not photos}


def _stored_photos(data: Dict[str, Any]) -> List[Dict[str, str]]:
    urls = []
    many = data.get("image_urls") if isinstance(data.get("image_urls"), list) else []
    for url in many:
        if isinstance(url, str) and url.startswith("http") and url not in urls:
            urls.append(url)
    image = data.get("image_url")
    if isinstance(image, str) and image.startswith("http") and image not in urls:
        urls.insert(0, image)
    return _as_photos(urls[:8])


def _as_photos(urls: List[str]) -> List[Dict[str, str]]:
    photos = []
    for index, url in enumerate(urls):
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        photos.append({"url": url, "caption": "Photo of the home" if index == 0 else "Another photo of the home"})
    return photos
