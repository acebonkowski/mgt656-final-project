import logging
import secrets
from fractions import Fraction

from django.conf import settings
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from abtest.models import Click, Impression, Variant

logger = logging.getLogger(__name__)

SESSION_KEY = "abtest"
VARIANTS = [Variant.KUDOS.value, Variant.THANKS.value]


def choose_variant():
    """Fair 50/50 pick for a new visitor."""
    return secrets.choice(VARIANTS)


def _session_data(request):
    data = request.session.get(SESSION_KEY)
    if isinstance(data, dict) and data.get("variant") in VARIANTS and data.get("visitor_id"):
        return data
    return None


@never_cache
@require_GET
def page(request):
    data = _session_data(request)
    if data:
        # Returning visitor (reload, revisit, or the redirect after a click):
        # same variant, no new impression. If their row was deleted (e.g.
        # test-data cleanup), record it once more with the same variant.
        variant = data["variant"]
        Impression.objects.get_or_create(visitor_id=data["visitor_id"], defaults={"variant": variant})
    else:
        variant = choose_variant()
        impression = Impression.objects.create(variant=variant)
        request.session[SESSION_KEY] = {"visitor_id": str(impression.visitor_id), "variant": variant}
        logger.debug("A/B impression recorded: %s", variant)

    return render(request, "abtest/page.html", {
        "variant": variant,
        "members": settings.TEAM_MEMBER_NICKNAMES,
    })


@never_cache
@require_POST
def click(request):
    data = _session_data(request)
    if data:
        impression = Impression.objects.filter(visitor_id=data["visitor_id"]).first()
        if impression:
            _, created = Click.objects.get_or_create(impression=impression)
            if created:
                logger.debug("A/B click recorded: %s", impression.variant)
    return redirect("abtest:page")


def _click_rate(c):
    # Exact fraction (no float rounding); no impressions means a rate of 0.
    return Fraction(c["clicks"], c["impressions"]) if c["impressions"] else Fraction(0)


def preferred_variant(counts):
    """Variant with the strictly higher click rate. Ties and no data go to kudos."""
    if _click_rate(counts[Variant.THANKS]) > _click_rate(counts[Variant.KUDOS]):
        return Variant.THANKS.value
    return Variant.KUDOS.value


@never_cache
@require_GET
def stats(request):
    counts = {v: {"impressions": 0, "clicks": 0} for v in VARIANTS}
    rows = Impression.objects.values("variant").annotate(
        impressions=Count("id"), clicks=Count("click")
    )
    for row in rows:
        if row["variant"] in counts:
            counts[row["variant"]] = {"impressions": row["impressions"], "clicks": row["clicks"]}
    return JsonResponse({"preferred": preferred_variant(counts), **counts})
