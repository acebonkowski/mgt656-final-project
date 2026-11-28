"""
Settings page (#83): attendance visibility, profile photo, delete account.
Photo storage is mocked; nothing touches the network.
"""

import base64
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from core.models import Event, EventAttendance, ProfilePhoto
from core.photo_storage import StorageUnavailable

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def make_event(creator, name, visibility=Event.Visibility.EVERYONE, days=1):
    start = timezone.now() + timedelta(days=days)
    return Event.objects.create(
        image="events/1/x.jpg", name=name, description="d", category="music_performance",
        start_at=start, end_at=start + timedelta(hours=1), location="Yale",
        latitude=41.3, longitude=-72.9, creator=creator, visibility=visibility,
    )


class SettingsBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="me@yale.edu")
        self.profile = Profile.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.url = reverse("settings")


class AttendanceVisibilityTests(SettingsBase):
    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_default_is_everyone_and_checked(self):
        self.assertEqual(self.profile.attendance_visibility, "everyone")
        response = self.client.get(self.url)
        self.assertContains(response, 'value="everyone"\n                   checked')

    def test_offers_friends_program_school_everyone(self):
        response = self.client.get(self.url)
        for value in ("friends", "program", "school", "everyone"):
            self.assertContains(response, f'name="attendance_visibility" value="{value}"')

    def test_choice_is_saved_and_shown_again_on_reload(self):
        response = self.client.post(self.url, {"attendance_visibility": "program"})
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.attendance_visibility, "program")
        response = self.client.get(self.url)
        self.assertContains(response, 'value="program"\n                   checked')
        self.assertNotContains(response, 'value="everyone"\n                   checked')

    def test_invalid_choice_is_rejected_and_not_saved(self):
        response = self.client.post(self.url, {"attendance_visibility": "nobody"})
        self.assertEqual(response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.attendance_visibility, "everyone")

    def test_only_changes_own_profile(self):
        other = Profile.objects.create(user=get_user_model().objects.create_user(username="o@yale.edu"))
        self.client.post(self.url, {"attendance_visibility": "friends"})
        other.refresh_from_db()
        self.assertEqual(other.attendance_visibility, "everyone")


class SettingsPhotoTests(SettingsBase):
    def test_new_photo_replaces_old_and_shows_in_settings_and_header(self):
        with mock.patch("core.photo_views.photo_storage.upload"), \
                mock.patch("core.photo_views.validate_photo", return_value=(PNG, "image/png")):
            response = self.client.post(reverse("profile_photo"), {
                "photo": SimpleUploadedFile("p.png", PNG, content_type="image/png")})
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo_reference)
        page = self.client.get(self.url)
        self.assertContains(page, f'src="{reverse("profile_photo")}"')
        self.assertContains(page, 'id="profile-menu-photo"')  # header avatar

    def test_page_posts_photos_to_existing_endpoint(self):
        self.assertContains(self.client.get(self.url), f'action="{reverse("profile_photo")}"')


class DeleteAccountTests(SettingsBase):
    url_name = "delete_account"

    def setUp(self):
        super().setUp()
        self.delete_url = reverse(self.url_name)

    def test_get_asks_for_confirmation_and_deletes_nothing(self):
        response = self.client.get(self.delete_url)
        self.assertContains(response, "Type DELETE to confirm")
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_wrong_confirmation_does_not_delete(self):
        response = self.client.post(self.delete_url, {"confirm": "nope"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_delete_requires_login(self):
        self.client.logout()
        response = self.client.post(self.delete_url, {"confirm": "DELETE"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_confirmed_delete_removes_account_and_logs_out(self):
        response = self.client.post(self.delete_url, {"confirm": "DELETE"})
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Profile.objects.filter(pk=self.profile.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("map")).status_code, 302)

    def test_removes_the_users_own_data_but_not_others(self):
        other = get_user_model().objects.create_user(username="o@yale.edu")
        event = make_event(other, "Other's")
        EventAttendance.objects.create(user=self.user, event=event, status="going")
        self.client.post(self.delete_url, {"confirm": "DELETE"})
        self.assertFalse(EventAttendance.objects.exists())
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_hosted_events_upcoming_and_non_public_are_deleted_past_public_kept_hostless(self):
        upcoming = make_event(self.user, "Upcoming")
        past_private = make_event(self.user, "Past private", Event.Visibility.SCHOOL, days=-3)
        past_public = make_event(self.user, "Past public", days=-3)
        self.client.post(self.delete_url, {"confirm": "DELETE"})
        self.assertFalse(Event.objects.filter(pk__in=[upcoming.pk, past_private.pk]).exists())
        past_public.refresh_from_db()
        self.assertIsNone(past_public.creator)

    def test_photo_history_does_not_block_deletion_and_objects_are_removed(self):
        ProfilePhoto.objects.create(profile=self.profile, object_key="profiles/1/a.png", content_type="image/png")
        with mock.patch("core.settings_views.photo_storage.delete") as delete:
            self.client.post(self.delete_url, {"confirm": "DELETE"})
        delete.assert_called_once_with("profiles/1/a.png")
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_storage_outage_does_not_block_deletion(self):
        ProfilePhoto.objects.create(profile=self.profile, object_key="profiles/1/a.png", content_type="image/png")
        with mock.patch("core.settings_views.photo_storage.delete", side_effect=StorageUnavailable):
            response = self.client.post(self.delete_url, {"confirm": "DELETE"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
