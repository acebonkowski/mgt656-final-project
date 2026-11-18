"""
{% search_panel %} renders the event search panel (#35) on the map screen.

An inclusion tag, so the panel gets its choices from core.search without
changing map_view (#31).
"""

from django import template

from core.models import Event
from core.search import DEFAULT_RADIUS_MI, RADIUS_CHOICES, WHEN_CHOICES

register = template.Library()


@register.inclusion_tag("core/_search_panel.html", takes_context=True)
def search_panel(context):
    return {
        # AI search (#36) posts with Django's CSRF token.
        "csrf_token": context.get("csrf_token"),
        "categories": Event.Category.choices,
        "when_choices": WHEN_CHOICES,
        "radius_choices": RADIUS_CHOICES,
        "default_radius": f"{DEFAULT_RADIUS_MI:g}",
    }
