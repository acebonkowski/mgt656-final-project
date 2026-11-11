"""Private Supabase Storage via HTTP; no SDK or Supabase Auth.

Django authenticates users. Only the server holds the service-role key. Browser
requests never supply object keys, bucket names, or another user's identifier.
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings

logger = logging.getLogger(__name__)
MAX_PHOTO_BYTES = 5 * 1024 * 1024


class StorageUnavailable(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward service credentials to a redirect target.
        return None


def configured():
    return bool(settings.SUPABASE_STORAGE_URL and settings.SUPABASE_STORAGE_KEY)


def request(method, path, data=None, content_type="application/json"):
    base = settings.SUPABASE_STORAGE_URL.rstrip("/")
    parsed = urlsplit(base)
    if not configured() or parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
        raise StorageUnavailable("Profile photo storage is not configured.")
    key = settings.SUPABASE_STORAGE_KEY
    req = Request(base + "/storage/v1/" + path, data=data, method=method, headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": content_type,
        "x-upsert": "false", "Cache-Control": "private, no-store",
    })
    try:
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            body = response.read(MAX_PHOTO_BYTES + 1)
            if len(body) > MAX_PHOTO_BYTES:
                raise StorageUnavailable("Photo storage returned an oversized response.")
            return body
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        # Provider responses can contain internal details; do not expose them.
        logger.warning("Profile storage request failed (%s)", type(exc).__name__)
        raise StorageUnavailable("Profile photo storage is temporarily unavailable.") from exc


def object_path(object_key):
    return quote(settings.SUPABASE_PHOTO_BUCKET, safe="") + "/" + quote(object_key, safe="/")


def upload(object_key, data, content_type):
    request("POST", "object/" + object_path(object_key), data, content_type)


def download(object_key):
    return request("GET", "object/authenticated/" + object_path(object_key))


def ensure_bucket():
    """Explicit setup command only; never called from a user request or migration."""
    bucket = settings.SUPABASE_PHOTO_BUCKET
    try:
        raw = request("GET", "bucket/" + quote(bucket, safe=""))
    except StorageUnavailable as exc:
        cause = exc.__cause__
        # Supabase reports a missing bucket as 400 or 404 with a JSON error.
        # Do not treat bad credentials or other provider failures as 'missing'.
        if not isinstance(cause, HTTPError) or cause.code not in (400, 404):
            raise
        try:
            error = json.loads(cause.read())
        except (ValueError, OSError):
            raise exc
        if error.get("message") != "Bucket not found":
            raise exc
        request("POST", "bucket", json.dumps({
            "id": bucket, "name": bucket, "public": False,
            "file_size_limit": MAX_PHOTO_BYTES,
            "allowed_mime_types": ["image/jpeg", "image/png"],
        }).encode())
        raw = request("GET", "bucket/" + quote(bucket, safe=""))
    try:
        info = json.loads(raw)
        correct = (info.get("public") is False
                   and int(info.get("file_size_limit") or 0) == MAX_PHOTO_BYTES
                   and set(info.get("allowed_mime_types") or []) == {"image/jpeg", "image/png"})
    except (ValueError, TypeError, AttributeError):
        correct = False
    if not correct:
        raise StorageUnavailable("Bucket must be private, limited to 5 MB, and allow only JPEG/PNG. Review it in Supabase.")
