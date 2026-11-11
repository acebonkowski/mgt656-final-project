from django.conf import settings
from django.urls import path

from abtest import views
from abtest.hashing import nickname_hash

app_name = "abtest"

# Computed once at startup from the TEAM_NICKNAME setting.
PAGE_HASH = nickname_hash(settings.TEAM_NICKNAME)

urlpatterns = [
    path(PAGE_HASH, views.page, name="page"),
    path(f"{PAGE_HASH}/click", views.click, name="click"),
    path(f"{PAGE_HASH}/stats", views.stats, name="stats"),
]
