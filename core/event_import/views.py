import secrets
from threading import Thread

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .runner import acquire_lock, background_import, release_lock


@csrf_exempt  # Machine endpoint authenticated by secret header, never cookies.
@require_POST
def trigger_import(request):
    expected = settings.AGGREGATOR_TOKEN
    supplied = request.headers.get("Authorization", "")
    if not expected or not secrets.compare_digest(supplied.encode(), ("Bearer " + expected).encode()):
        return JsonResponse({"error": "Forbidden"}, status=403)
    token = acquire_lock()
    if token is None:
        return JsonResponse({"status": "already_running"}, status=202)
    try:
        Thread(target=background_import, args=(token,), daemon=True, name="event-import").start()
    except Exception:
        release_lock(token)
        return JsonResponse({"error": "Unable to start import"}, status=503)
    return JsonResponse({"status": "accepted", "run": token}, status=202)
