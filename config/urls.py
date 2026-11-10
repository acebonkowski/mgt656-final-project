from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("map/", views.map_view, name="map"),
    path("admin/", admin.site.urls),
]
