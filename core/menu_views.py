"""Temporary destinations until Friends (#39) and Settings (#83) land."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from accounts.models import Profile


@login_required
@never_cache
def friends(request):
    profile = Profile.objects.filter(user=request.user).first()
    return render(request, "core/menu_pending.html", {
        "title": "Friends", "message": "Finding friends and managing requests is coming soon.",
        "username": profile.username if profile else "",
    })


@login_required
@never_cache
def settings(request):
    return render(request, "core/menu_pending.html", {
        "title": "Settings", "message": "Account settings are coming soon.",
    })
