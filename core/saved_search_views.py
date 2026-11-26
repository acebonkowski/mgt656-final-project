"""
Saved search endpoints (#37). Deleting and replacing a saved search need an
explicit confirmation (confirm=1); without it nothing changes. A user can only
touch their own searches and suggestions (anyone else's id is a 404).
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from core import saved_searches
from core.models import SavedSearch, SearchSuggestion

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


def queries_url():
    return reverse("my_events_list", args=["suggested"]) + "?tab=queries"


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def delete_search_view(request, search_id):
    """
    GET shows the confirmation page and deletes nothing. POST confirm=1 deletes
    the saved search and returns to My Queries; without confirm=1 nothing changes.
    """
    saved = get_object_or_404(SavedSearch, pk=search_id, user=request.user)
    if request.method == "GET":
        return render(request, "core/saved_search_confirm_delete.html", {
            "saved": saved,
            "summary": saved_searches.describe_filters(saved.filters),
            "cancel_url": queries_url(),
        })
    if not confirmed(request):
        return error(CONFIRM_NEEDED, 409)
    saved_searches.delete_search(saved)
    return redirect(queries_url())


@login_required
@never_cache
@require_POST
def hide_suggestion_view(request, event_id):
    """The cross on a Suggested card: hide it for good, then go back where the user was."""
    suggestion = get_object_or_404(SearchSuggestion, user=request.user, event_id=event_id)
    if not suggestion.hidden:
        suggestion.hidden = True
        suggestion.save(update_fields=["hidden"])
    target = request.POST.get("next", "")
    safe = target.startswith("/my-events/") and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    return redirect(target if safe else reverse("my_events"))
