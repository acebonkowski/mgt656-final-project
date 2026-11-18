import json
import logging
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class GeocodingUnavailable(Exception):
    pass


def search(query):
    if not settings.MAP_API_KEY:
        raise GeocodingUnavailable("Map geocoding is not configured.")
    url = (
        "https://api.maptiler.com/geocoding/"
        + quote(query, safe="")
        + ".json"
        + "?key="
        + quote(settings.MAP_API_KEY, safe="")
        + "&limit=5&language=en&proximity=-72.9279,41.3083"
    )
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("MapTiler geocoding failed (%s)", type(exc).__name__)
        raise GeocodingUnavailable("Address search is temporarily unavailable.") from exc

    suggestions = []
    for feature in payload.get("features", []):
        center = feature.get("center")
        if not isinstance(center, list) or len(center) != 2:
            continue
        suggestions.append({
            "address": feature.get("place_name")
            or feature.get("place_name_en")
            or feature.get("text")
            or "",
            "latitude": center[1],
            "longitude": center[0],
        })
    return [item for item in suggestions if item["address"]]
