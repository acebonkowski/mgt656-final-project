from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("admin/", admin.site.urls),
]
