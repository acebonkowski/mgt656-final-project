import json
import logging
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

COORDINATE_DECIMAL_PLACES = 6


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
            # Event coordinates are stored with 6 decimal places (~0.1 m);
            # MapTiler returns more, which the form would reject (#55).
            "latitude": round(center[1], COORDINATE_DECIMAL_PLACES),
            "longitude": round(center[0], COORDINATE_DECIMAL_PLACES),
        })
    return [item for item in suggestions if item["address"]]
