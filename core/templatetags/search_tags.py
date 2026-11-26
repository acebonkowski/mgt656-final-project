"""
{% search_panel %} renders the event search panel (#35) on the map screen.

An inclusion tag, so the panel gets its choices from core.search without
changing map_view (#31).
"""

from django import template

from core.models import Event, SavedSearch
from core.search import DEFAULT_RADIUS_MI, RADIUS_CHOICES, WHEN_CHOICES

register = template.Library()


def search_being_edited(request):
    """
    The saved search (#37) My Queries sent the user here to edit
    (/map/?mode=ai&edit=<id>). Only the owner's own search counts; anything else
    is ignored.
    """
    raw = request.GET.get("edit", "") if request else ""
    if not (raw.isdigit() and len(raw) < 10 and request.user.is_authenticated):
        return None
    return SavedSearch.objects.filter(pk=int(raw), user=request.user).first()


@register.inclusion_tag("core/_search_panel.html", takes_context=True)
def search_panel(context):
    return {
        "edit_search": search_being_edited(context.get("request")),
        # AI search (#36) posts with Django's CSRF token.
        "csrf_token": context.get("csrf_token"),
        "categories": Event.Category.choices,
        "when_choices": WHEN_CHOICES,
        "radius_choices": RADIUS_CHOICES,
        "default_radius": f"{DEFAULT_RADIUS_MI:g}",
    }
