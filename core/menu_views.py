"""Temporary destination until Settings (#83) lands. Friends is core.friends_views (#96)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@login_required
@never_cache
def settings(request):
    return render(request, "core/menu_pending.html", {
        "title": "Settings", "message": "Account settings are coming soon.",
    })
