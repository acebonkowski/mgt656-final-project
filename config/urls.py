from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views
from core import views
from core.photo_views import profile_photo
from core.ai_search_views import ai_search_reset_view, ai_search_view
from core.search_views import search_events_view

urlpatterns = [
    path("", accounts_views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/photo/", profile_photo, name="profile_photo"),
    path("map/", views.map_view, name="map"),
    path("map/tiles/<int:z>/<int:x>/<int:y>.pbf", views.map_tile, name="map_tile"),
    path("event-photo/<path:object_key>", views.event_photo, name="event_photo"),
    path("event-image/generate/", views.generate_event_image, name="generate_event_image"),
    path("map/geocode/", views.geocode_address, name="geocode_address"),
    path("map/duplicate/", views.duplicate_event, name="duplicate_event"),
    path("events/search/", search_events_view, name="search_events"),
    path("events/search/ai/", ai_search_view, name="ai_search"),
    path("events/search/ai/reset/", ai_search_reset_view, name="ai_search_reset"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/popup/", views.event_detail_popup, name="event_detail_popup"),
    path("events/<int:event_id>/calendar.ics", views.event_calendar, name="event_calendar"),
    path("events/<int:event_id>/edit/", views.edit_event, name="edit_event"),
    path("events/<int:event_id>/delete/", views.delete_event, name="delete_event"),
    # Before admin.site.urls: admin's password login is replaced by the Welcome screen.
    path("admin/login/", accounts_views.admin_login, name="admin_login"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("abtest.urls")),
]
