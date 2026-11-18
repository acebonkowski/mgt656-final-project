"""
AI search endpoints (#36). OpenRouter is called only here on the server, never
from the browser. Every failure returns a friendly JSON error; manual search
keeps working.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core import ai_limits, ai_search, llm
from core.models import AIUsage
from core.search_views import event_json

logger = logging.getLogger(__name__)

UNAVAILABLE = "AI search isn't available right now. Try again in a moment; manual search still works."
UNREADABLE = "The AI's answer didn't make sense. Try rephrasing, or use the filters."


def error(message, status, **extra):
    return JsonResponse({"error": message, **extra}, status=status)


@login_required
@never_cache
@require_POST
def ai_search_view(request):
    """POST message=... -> {reply, filters, notes, count, events}."""
    message = (request.POST.get("message") or "").strip()
    if not message:
        return error("Type what you're looking for.", 400)
    if len(message) > ai_search.MAX_MESSAGE_CHARS:
        return error(f"Keep your message under {ai_search.MAX_MESSAGE_CHARS} characters.", 400)
    if not llm.configured():
        return error(UNAVAILABLE, 503)

    now = timezone.now()
    try:
        ai_limits.reserve(request.user, AIUsage.Kind.SEARCH, now=now)
    except ai_limits.LimitReached as exc:
        return error(str(exc), 429, limit=True)

    history = request.session.get(ai_search.HISTORY_SESSION_KEY, [])
    try:
        result = ai_search.search(message, history, now=now)
    except llm.LLMInvalidResponse:
        return error(UNREADABLE, 502)
    except llm.LLMUnavailable:
        return error(UNAVAILABLE, 503)

    history = (history + result["history"])[-ai_search.MAX_HISTORY_MESSAGES:]
    request.session[ai_search.HISTORY_SESSION_KEY] = history
    events = [event_json(event) for event in result["events"]]
    return JsonResponse({
        "reply": result["reply"],
        "filters": result["filters"],
        "notes": result["notes"],
        "count": len(events),
        "events": events,
    })


@login_required
@never_cache
@require_POST
def ai_search_reset_view(request):
    """"New chat": forget the conversation."""
    request.session.pop(ai_search.HISTORY_SESSION_KEY, None)
    return JsonResponse({"ok": True})
