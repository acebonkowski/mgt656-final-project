"""Temporary destinations until Friends (#39) lands."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@login_required
@never_cache
def friends(request):
    return render(request, "core/menu_pending.html", {
        "title": "Friends", "message": "Finding friends and managing requests is coming soon.",
    })
