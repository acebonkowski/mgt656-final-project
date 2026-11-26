"""
Going status endpoint (#84). Kept apart from core/views.py like search_views.py.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.attendance import can_answer
from core.models import Event, EventAttendance
from core.visibility import can_view


@login_required
@never_cache
@require_POST
def set_going(request, event_id):
    """
    POST /events/<id>/going/ with status = going, maybe, not_going, or empty to
    clear the answer. Returns the saved status ("" when cleared).
    """
    event = get_object_or_404(Event, pk=event_id)
    if not can_view(request.user, event):
        raise Http404
    if not can_answer(request.user, event):
        return JsonResponse({"error": "You can't answer for this event."}, status=400)

    status = request.POST.get("status", "")
    if status == "":
        EventAttendance.objects.filter(user=request.user, event=event).delete()
        return JsonResponse({"status": ""})
    if status not in EventAttendance.Status.values:
        return JsonResponse({"error": "Unknown status."}, status=400)

    EventAttendance.objects.update_or_create(
        user=request.user, event=event, defaults={"status": status}
    )
    return JsonResponse({"status": status})
