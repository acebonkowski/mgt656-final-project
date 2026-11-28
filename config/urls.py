from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views
from core import views, menu_views
from core.photo_views import profile_photo
from core.event_import.views import trigger_import
from core.ai_search_views import ai_search_reset_view, ai_search_view
from core.attendance_views import set_going
from core.favorite_views import set_favorite
from core.my_events_views import my_events, my_events_list
from core.saved_search_views import (
    delete_search_view, hide_suggestion_view, save_search_view, update_search_view,
)
from core.search_views import search_events_view

urlpatterns = [
    path("internal/import-events/", trigger_import, name="trigger_event_import"),
    path("", accounts_views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/photo/", profile_photo, name="profile_photo"),
    path("username/", accounts_views.choose_username, name="username"),
    path("map/", views.map_view, name="map"),
    path("map/tiles/<int:z>/<int:x>/<int:y>.pbf", views.map_tile, name="map_tile"),
    path("event-photo/<path:object_key>", views.event_photo, name="event_photo"),
    path("event-image/generate/", views.generate_event_image, name="generate_event_image"),
    path("map/geocode/", views.geocode_address, name="geocode_address"),
    path("map/duplicate/", views.duplicate_event, name="duplicate_event"),
    path("friends/", menu_views.friends, name="friends"),
    path("settings/", menu_views.settings, name="settings"),
    path("my-events/", my_events, name="my_events"),
    path("my-events/<slug:row>/", my_events_list, name="my_events_list"),
    path("my-events/suggested/<int:event_id>/hide/", hide_suggestion_view, name="hide_suggestion"),
    path("events/search/", search_events_view, name="search_events"),
    path("events/search/ai/", ai_search_view, name="ai_search"),
    path("events/search/ai/reset/", ai_search_reset_view, name="ai_search_reset"),
    path("saved-searches/", save_search_view, name="save_search"),
    path("saved-searches/<int:search_id>/update/", update_search_view, name="update_saved_search"),
    path("saved-searches/<int:search_id>/delete/", delete_search_view, name="delete_saved_search"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/favorite/", set_favorite, name="set_favorite"),
    path("events/<int:event_id>/going/", set_going, name="set_going"),
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
