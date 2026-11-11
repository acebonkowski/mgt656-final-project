from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views
from core import views
from core.photo_views import profile_photo

urlpatterns = [
    path("", accounts_views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/photo/", profile_photo, name="profile_photo"),
    path("map/", views.map_view, name="map"),
    # Before admin.site.urls: admin's password login is replaced by the Welcome screen.
    path("admin/login/", accounts_views.admin_login, name="admin_login"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("abtest.urls")),
]
