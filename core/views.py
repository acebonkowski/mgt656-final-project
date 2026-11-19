import logging
import sqlite3
from contextlib import closing
from uuid import uuid4
import base64
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, IntegrityError, connection
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.text import slugify

from core.forms import EventForm, OnboardingForm
from core.ics import build_ics
from accounts.models import Profile
from core.models import Event, Program
from core.map_places import YALE_AREA_PLACES
from core import photo_storage
from core import llm
from core.photo_validation import validate_event_photo
from core import geocoding
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def onboarding(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = OnboardingForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Update only onboarding fields so a concurrent photo upload is preserved.
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            profile.display_name = form.cleaned_data["display_name"]
            profile.program = form.cleaned_data["program"]
            profile.onboarding_complete = True
            profile.save(update_fields=["display_name", "program", "onboarding_complete", "updated_at"])
        return redirect(getattr(settings, "ONBOARDING_SUCCESS_URL", "home"))
    return render(request, "core/onboarding.html", {
        "form": form,
        "profile": profile,
        "programs": list(Program.objects.filter(school__is_active=True).values("id", "school_id", "name")),
    })

logger = logging.getLogger(__name__)

# Centre of New Haven, CT, as [latitude, longitude].
NEW_HAVEN_CENTER = [41.3083, -72.9279]
NEW_HAVEN_ZOOM = 13
NEW_HAVEN_BOUNDS = [-72.99, 41.26, -72.86, 41.36]
MAP_TILE_MIN_ZOOM = 8
MAP_TILE_MAX_ZOOM = 16


def find_duplicate_event(location, date, start_time, end_time):
    new_york = ZoneInfo("America/New_York")
    start_at = datetime.combine(date, start_time, tzinfo=new_york)
    end_at = datetime.combine(date, end_time, tzinfo=new_york)
    return Event.objects.filter(
        location=location,
        start_at=start_at,
        end_at=end_at,
    ).first()


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def map_view(request):
    """Home screen: a locally served OpenStreetMap basemap of New Haven."""
    map_enabled = settings.LOCAL_MAP_TILES_PATH.is_file()
    if not map_enabled:
        logger.error("Local map tile archive is missing: %s", settings.LOCAL_MAP_TILES_PATH)
    form = EventForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
    )
    if request.method == "POST" and form.is_valid():
        duplicate = find_duplicate_event(
            form.cleaned_data["location"],
            form.cleaned_data["date"],
            form.cleaned_data["start_time"],
            form.cleaned_data["end_time"],
        )
        if duplicate:
            form.add_error(None, "An event already exists at this location and time.")
        else:
            image_data, content_type = form.event_image
            extension = "jpg" if content_type == "image/jpeg" else "png"
            image_key = f"events/{request.user.pk}/{uuid4().hex}.{extension}"
            try:
                photo_storage.upload(
                    image_key,
                    image_data,
                    content_type,
                    bucket=settings.SUPABASE_EVENT_PHOTO_BUCKET,
                )
            except photo_storage.StorageUnavailable as exc:
                form.add_error("image", str(exc))
            else:
                try:
                    with transaction.atomic():
                        form.save(request.user, image_key=image_key)
                except IntegrityError:
                    form.add_error(None, "An event already exists at this location and time.")
                else:
                    return redirect("map")
    if request.method == "POST":
        # Field names only, never values, so the reason shows in the logs (#57).
        logger.info("Create event rejected: %s", ", ".join(sorted(form.errors)))

    active_events = Event.objects.filter(end_at__gt=timezone.now())
    event_data = [
        {
            "id": event.pk,
            "url": reverse("event_detail", args=[event.pk]),
            "name": event.name,
            "location": event.location,
            "latitude": float(event.latitude),
            "longitude": float(event.longitude),
            "price": event.price_label,
        }
        for event in active_events
    ]
    map_config = {
        "center": NEW_HAVEN_CENTER,
        "bounds": NEW_HAVEN_BOUNDS,
        "zoom": NEW_HAVEN_ZOOM,
        "minZoom": MAP_TILE_MIN_ZOOM,
        "maxZoom": MAP_TILE_MAX_ZOOM,
        "tileUrl": reverse("map_tile", kwargs={"z": 8, "x": 0, "y": 0}).replace(
            "/8/0/0.pbf", "/{z}/{x}/{y}.pbf"
        ),
        "events": event_data,
        "places": YALE_AREA_PLACES,
    }
    return render(request, "core/map.html", {
        "map_config": map_config,
        "map_enabled": map_enabled,
        "event_form": form,
    })


def map_tile(request, z, x, y):
    """Serve one local OSM vector tile from the app's MBTiles archive."""
    if z < MAP_TILE_MIN_ZOOM or z > MAP_TILE_MAX_ZOOM or x >= 2**z or y >= 2**z:
        return HttpResponse(status=404)

    tile_row = 2**z - y - 1
    tile_uri = settings.LOCAL_MAP_TILES_PATH.resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(tile_uri, uri=True)) as database:
            result = database.execute(
                "SELECT tile_data FROM tiles "
                "WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                (z, x, tile_row),
            ).fetchone()
    except sqlite3.Error:
        logger.exception("Could not read local map tile z=%s x=%s y=%s", z, x, y)
        return HttpResponse("Map tiles are temporarily unavailable.", status=503)

    if result is None:
        return HttpResponse(status=204)

    response = HttpResponse(result[0], content_type="application/vnd.mapbox-vector-tile")
    if result[0][:2] == b"\x1f\x8b":
        response["Content-Encoding"] = "gzip"
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def event_photo(request, object_key):
    # Public (#32, team decision): shared event pages are viewable logged out,
    # so their image must be too. Only keys that belong to an event are served.
    event = Event.objects.filter(image=object_key).first()
    if not event:
        raise Http404
    try:
        data = photo_storage.download(
            object_key,
            bucket=settings.SUPABASE_EVENT_PHOTO_BUCKET,
        )
    except photo_storage.StorageUnavailable:
        return HttpResponse(status=503)
    content_type = "image/jpeg" if object_key.lower().endswith(".jpg") else "image/png"
    response = HttpResponse(data, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=3600"
    return response


@login_required
@never_cache
@require_http_methods(["POST"])
def generate_event_image(request):
    prompt = (request.POST.get("prompt") or "").strip()
    if not prompt:
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        prompt = "Create an attractive event poster image"
        if name:
            prompt += f" for {name}"
        if description:
            prompt += f": {description}"
        prompt += ". Do not include text or logos."
    try:
        data, content_type = llm.generate_image(prompt)
        if content_type not in ("image/png", "image/jpeg"):
            raise llm.LLMUnavailable("The AI image service returned an unsupported format.")
        upload = SimpleUploadedFile(
            "generated-event-image",
            data,
            content_type=content_type,
        )
        try:
            clean_data, clean_type = validate_event_photo(upload)
        except ValidationError as exc:
            return JsonResponse({"error": exc.messages[0]}, status=400)
    except llm.LLMUnavailable as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    data_url = f"data:{clean_type};base64," + base64.b64encode(clean_data).decode("ascii")
    return JsonResponse({"image": data_url})


@login_required
@never_cache
@require_http_methods(["GET"])
def geocode_address(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 3:
        return JsonResponse({"suggestions": []})
    try:
        suggestions = geocoding.search(query)
    except geocoding.GeocodingUnavailable as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    return JsonResponse({"suggestions": suggestions})


@login_required
@never_cache
@require_http_methods(["GET"])
def duplicate_event(request):
    location = (request.GET.get("location") or "").strip()
    date_value = (request.GET.get("date") or "").strip()
    start_value = (request.GET.get("start_time") or "").strip()
    end_value = (request.GET.get("end_time") or "").strip()
    if not all((location, date_value, start_value, end_value)):
        return JsonResponse({"match": None})
    try:
        date = datetime.strptime(date_value, "%Y-%m-%d").date()
        start_time = datetime.strptime(start_value, "%H:%M").time()
        end_time = datetime.strptime(end_value, "%H:%M").time()
    except ValueError:
        return JsonResponse({"match": None})
    event = find_duplicate_event(location, date, start_time, end_time)
    if not event:
        return JsonResponse({"match": None})
    return JsonResponse({
        "match": {
            "id": event.pk,
            "name": event.name,
            "detail_url": f"/events/{event.pk}/popup/",
        }
    })


@never_cache
def event_detail(request, event_id):
    """Shareable event page (#32): public, so a shared link works logged out."""
    event = Event.objects.filter(pk=event_id).first()
    if not event:
        raise Http404
    page_path = reverse("event_detail", kwargs={"event_id": event.pk})
    return render(request, "core/event_detail.html", {
        "event": event,
        "popup": False,
        "share_url": request.build_absolute_uri(page_path),
        # Visitors who join from a shared link come back to this event.
        "join_url": f"{reverse('accounts:welcome')}?{urlencode({'next': page_path})}",
    })


@never_cache
def event_calendar(request, event_id):
    """Download one event as an .ics file (America/New_York times)."""
    event = get_object_or_404(Event, pk=event_id)
    response = HttpResponse(build_ics(event), content_type="text/calendar; charset=utf-8")
    filename = f"{slugify(event.name) or 'event'}.ics"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@never_cache
def event_detail_popup(request, event_id):
    event = Event.objects.filter(pk=event_id).first()
    if not event:
        raise Http404
    return render(request, "core/event_detail.html", {
        "event": event,
        "popup": True,
    })


def event_form_initial(event):
    new_york = ZoneInfo("America/New_York")
    start_at = event.start_at.astimezone(new_york)
    end_at = event.end_at.astimezone(new_york)
    return {
        "name": event.name,
        "description": event.description,
        "category": event.category,
        "date": start_at.date(),
        "start_time": start_at.time().replace(tzinfo=None),
        "end_time": end_at.time().replace(tzinfo=None),
        "location": event.location,
        "location_confirmed": event.location,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "price": event.price,
        "link": event.link,
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def edit_event(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if event.creator_id != request.user.pk:
        raise PermissionDenied

    initial = event_form_initial(event)
    form = EventForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        initial=initial,
        existing_image=event.image,
    )
    if request.method == "POST" and form.is_valid():
        duplicate = find_duplicate_event(
            form.cleaned_data["location"],
            form.cleaned_data["date"],
            form.cleaned_data["start_time"],
            form.cleaned_data["end_time"],
        )
        if duplicate and duplicate.pk != event.pk:
            form.add_error(None, "An event already exists at this location and time.")
        else:
            image_key = event.image
            if getattr(form, "event_image", None):
                image_data, content_type = form.event_image
                extension = "jpg" if content_type == "image/jpeg" else "png"
                image_key = f"events/{request.user.pk}/{uuid4().hex}.{extension}"
                try:
                    photo_storage.upload(
                        image_key,
                        image_data,
                        content_type,
                        bucket=settings.SUPABASE_EVENT_PHOTO_BUCKET,
                    )
                except photo_storage.StorageUnavailable as exc:
                    form.add_error("image", str(exc))
            if not form.errors:
                try:
                    with transaction.atomic():
                        form.save(request.user, image_key=image_key, instance=event)
                except IntegrityError:
                    form.add_error(None, "An event already exists at this location and time.")
                else:
                    return redirect("event_detail", event_id=event.pk)

    return render(request, "core/edit_event.html", {
        "event": event,
        "event_form": form,
    })


@login_required
@never_cache
@require_http_methods(["POST"])
def delete_event(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if event.creator_id != request.user.pk:
        raise PermissionDenied
    event.delete()
    return redirect("map")


def healthz(request):
    """Liveness + database check, used as Render's health check path."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Health check failed: database unreachable")
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
