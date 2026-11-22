"""Bounded public-feed adapters. Never log URLs containing credentials."""
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings

from core.models import EVENT_DESCRIPTION_MAX_LENGTH, EVENT_NAME_MAX_LENGTH, fit_to_limit

from .categories import classify
from .ics import Candidate, Preview, aware_datetime, parse_feed

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_HOSTS = {"yaleconnect.yale.edu", "groups.som.yale.edu",
                 "static-prod-us-east-1.campusgroups.com", "app.ticketmaster.com"}


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.port not in (None, 443):
        raise ValueError("Feed URL is not an approved HTTPS source")


class FeedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        # API-key-bearing requests must never redirect to another host.
        if urlsplit(req.full_url).hostname == "app.ticketmaster.com":
            raise ValueError("Ticketmaster redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, deadline):
    validate_url(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Import deadline reached")
    request = Request(url, headers={"User-Agent": "MGT656-EventImporter/1.0", "Accept": "text/calendar, application/json"})
    with build_opener(FeedRedirect()).open(request, timeout=min(10, remaining)) as response:
        chunks, size = [], 0
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("Import deadline reached")
            chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("Feed exceeds size limit")
            chunks.append(chunk)
    return b"".join(chunks)


def parse_ticketmaster(payload, *, now, until):
    result = Preview()
    for raw in payload.get("_embedded", {}).get("events", []):
        result.counts["seen"] += 1
        try:
            dates = raw["dates"]
            if dates.get("status", {}).get("code") in {"cancelled", "postponed"}:
                result.counts["cancelled"] += 1
                continue
            start = aware_datetime(datetime.fromisoformat(dates["start"]["dateTime"].replace("Z", "+00:00")))
            # Do not invent an end time if the provider does not supply it.
            end = aware_datetime(datetime.fromisoformat(dates["end"]["dateTime"].replace("Z", "+00:00")))
            if start < now:
                result.counts["past_start"] += 1
                continue
            if start >= until:
                result.counts["outside_window"] += 1
                continue
            if end <= start:
                raise ValueError("Invalid interval")
            venue = raw["_embedded"]["venues"][0]
            city, state = venue["city"]["name"], venue["state"]["stateCode"]
            if city.casefold() != "new haven" or state != "CT":
                result.counts["outside_city"] += 1
                continue
            name, link = raw["name"], raw["url"]
            if not name or urlsplit(link).scheme not in {"https", "http"}:
                raise ValueError("Invalid event")
            description = raw.get("info", "") or raw.get("pleaseNote", "")
            segments = [c.get("segment", {}).get("name", "") for c in raw.get("classifications", [])]
            mapping = {"Music": "music_performance", "Arts & Theatre": "music_performance",
                       "Film": "art_film_exhibits", "Sports": "sports_outdoors_wellness"}
            category = next((mapping[s] for s in segments if s in mapping), None)
            category, method = (category, "mapping") if category else classify([], f"{name} {description}")
            # A range minimum is not an exact ticket price; preserve as unknown.
            ranges = raw.get("priceRanges", [])
            price = next((Decimal(str(p["min"])) for p in ranges if p.get("currency") == "USD"
                          and p.get("min") is not None and p.get("min") == p.get("max")), None)
            location = ", ".join(filter(None, [venue.get("name"), venue.get("address", {}).get("line1"), city, state]))
            coordinates = venue.get("location", {})
            result.events.append(Candidate("ticketmaster", str(raw["id"]),
                                           fit_to_limit(name, EVENT_NAME_MAX_LENGTH),
                                           fit_to_limit(description, EVENT_DESCRIPTION_MAX_LENGTH),
                                           start, end, location, link, category, method, price,
                                           coordinates.get("latitude"), coordinates.get("longitude"), city, state))
            result.counts["prepared"] += 1
        except (KeyError, ValueError, TypeError, IndexError, ArithmeticError):
            result.counts["invalid_or_unsupported"] += 1
    return result


def source_batches(source, *, now, until, deadline):
    if source in {"yale_connect", "som"}:
        url = settings.AGGREGATOR_YALE_URL if source == "yale_connect" else settings.AGGREGATOR_SOM_URL
        yield parse_feed(fetch(url, deadline), source, now=now, until=until)
        return
    if source != "ticketmaster":
        raise ValueError("Unsupported source")
    if not settings.TICKETMASTER_API_KEY:
        raise ValueError("Ticketmaster key is not configured")
    for page in range(5):  # API deep-paging limit: size * page < 1000.
        if page:
            time.sleep(0.25)  # Below the documented five requests/second limit.
        params = {"apikey": settings.TICKETMASTER_API_KEY, "city": "New Haven", "stateCode": "CT",
                  "size": 200, "page": page, "sort": "date,asc",
                  "startDateTime": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "endDateTime": until.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        payload = json.loads(fetch("https://app.ticketmaster.com/discovery/v2/events.json?" + urlencode(params), deadline))
        batch = parse_ticketmaster(payload, now=now, until=until)
        if page == 4 and payload.get("page", {}).get("totalPages", 1) > 5:
            batch.counts["pagination_limit"] += 1
        yield batch
        if page + 1 >= payload.get("page", {}).get("totalPages", 1):
            break
