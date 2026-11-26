"""
Saved search endpoints (#37). Deleting and replacing a saved search need an
explicit confirmation (confirm=1); without it nothing changes. A user can only
touch their own searches (anyone else's id is a 404).
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core import saved_searches
from core.models import SavedSearch

CONFIRM_NEEDED = "Please confirm first. Nothing was changed."


def error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def confirmed(request):
    return request.POST.get("confirm") == "1"


def search_json(saved):
    return {"id": saved.pk, "label": saved.label, "filters": saved.filters}


@login_required
@never_cache
@require_POST
def save_search_view(request):
    """POST filters=<json> [label=...] -> the saved search (201, or 200 if it was already saved)."""
    try:
        saved, created = saved_searches.save_search(
            request.user, request.POST.get("filters"), request.POST.get("label", "")
        )
    except saved_searches.SavedSearchError as exc:
        return error(str(exc))
    return JsonResponse(search_json(saved), status=201 if created else 200)


@login_required
@never_cache
@require_POST
def update_search_view(request, search_id):
    """POST confirm=1 filters=<json> [label=...] -> replace the saved search."""
    saved = get_object_or_404(SavedSearch, pk=search_id, user=request.user)
    if not confirmed(request):
        return error(CONFIRM_NEEDED, 409)
    try:
        saved_searches.update_search(
            saved, request.POST.get("filters"), request.POST.get("label", "")
        )
    except saved_searches.SavedSearchError as exc:
        return error(str(exc))
    return JsonResponse(search_json(saved))


@login_required
@never_cache
@require_POST
def delete_search_view(request, search_id):
    """POST confirm=1 -> delete the saved search."""
    saved = get_object_or_404(SavedSearch, pk=search_id, user=request.user)
    if not confirmed(request):
        return error(CONFIRM_NEEDED, 409)
    saved_searches.delete_search(saved)
    return JsonResponse({"ok": True})
