from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.models import Profile
from core.models import ProfilePhoto
from core import photo_storage
from core.photo_validation import validate_photo


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def profile_photo(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        if not profile.photo_reference:
            raise Http404
        photo = ProfilePhoto.objects.filter(profile=profile, object_key=profile.photo_reference, archived_at=None).first()
        if not photo:
            raise Http404
        try:
            data = photo_storage.download(photo.object_key)
        except photo_storage.StorageUnavailable:
            return HttpResponse(status=503)
        response = HttpResponse(data, content_type=photo.content_type)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    files = request.FILES  # Run bounded upload parsing before checking its error.
    if getattr(request, "photo_upload_error", None):
        return JsonResponse({"error": request.photo_upload_error}, status=400)
    action = request.POST.get("action", "upload")
    if action not in ("upload", "remove"):
        return JsonResponse({"error": "Unknown photo action."}, status=400)
    data = content_type = None
    if action == "upload":
        upload = files.get("photo")
        if not upload:
            return JsonResponse({"error": "Choose a JPEG or PNG photo."}, status=400)
        try:
            data, content_type = validate_photo(upload)
        except ValidationError as exc:
            return JsonResponse({"error": exc.messages[0]}, status=400)
        except photo_storage.StorageUnavailable:
            return JsonResponse({"error": "Photo uploads are temporarily unavailable. You can continue without a photo."}, status=503)

    # Unique keys, no overwrites. Keep an upload record even if the network fails
    # after accepting the object, so any orphan remains traceable and recoverable.
    photo = None
    if action == "upload":
        extension = "jpg" if content_type == "image/jpeg" else "png"
        photo = ProfilePhoto.objects.create(profile=profile,
            object_key=f"profiles/{request.user.pk}/{uuid4().hex}.{extension}",
            content_type=content_type, archived_at=timezone.now())
        try:
            photo_storage.upload(photo.object_key, data, content_type)
        except photo_storage.StorageUnavailable:
            return JsonResponse({"error": "We couldn't save your photo. Please try again. Your previous photo is unchanged."}, status=503)

    with transaction.atomic():
        profile = Profile.objects.select_for_update().get(pk=profile.pk)
        ProfilePhoto.objects.filter(profile=profile, archived_at=None).update(archived_at=timezone.now())
        profile.photo_reference = photo.object_key if photo else ""
        profile.save(update_fields=["photo_reference", "updated_at"])
        if photo:
            photo.archived_at = None
            photo.save(update_fields=["archived_at"])
    return JsonResponse({"has_photo": bool(photo),
                         "url": reverse("profile_photo") + f"?v={photo.pk}" if photo else None})
