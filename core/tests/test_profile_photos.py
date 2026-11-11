import base64
import importlib.util
from io import BytesIO
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile
from core.models import ProfilePhoto
from core.photo_storage import MAX_PHOTO_BYTES, StorageUnavailable
from core.photo_validation import validate_photo

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def upload(data=PNG, mime="image/png"):
    return SimpleUploadedFile("photo.png", data, content_type=mime)


class PhotoEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="photo@yale.edu")
        self.profile = Profile.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.url = reverse("profile_photo")
        self.storage = mock.patch("core.photo_views.photo_storage.upload").start()
        self.validator = mock.patch("core.photo_views.validate_photo", return_value=(PNG, "image/png")).start()
        self.addCleanup(mock.patch.stopall)

    def test_upload_replace_remove_retains_history_and_never_marks_onboarding_complete(self):
        response = self.client.post(self.url, {"photo": upload()})
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        first_key = self.profile.photo_reference
        self.assertTrue(first_key.startswith(f"profiles/{self.user.pk}/"))
        self.assertFalse(self.profile.onboarding_complete)
        self.client.post(self.url, {"photo": upload()})
        self.profile.refresh_from_db()
        self.assertNotEqual(first_key, self.profile.photo_reference)
        self.assertIsNotNone(ProfilePhoto.objects.get(object_key=first_key).archived_at)
        response = self.client.post(self.url, {"action": "remove"})
        self.assertFalse(response.json()["has_photo"])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_reference, "")
        self.assertEqual(ProfilePhoto.objects.filter(profile=self.profile, archived_at__isnull=False).count(), 2)
        self.assertEqual(self.storage.call_count, 2)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_failed_upload_preserves_previous_photo(self):
        self.client.post(self.url, {"photo": upload()})
        self.profile.refresh_from_db()
        previous = self.profile.photo_reference
        self.storage.side_effect = StorageUnavailable("provider down")
        self.assertEqual(self.client.post(self.url, {"photo": upload()}).status_code, 503)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_reference, previous)
        self.assertIsNone(ProfilePhoto.objects.get(object_key=previous).archived_at)

    def test_bad_image_validation_rejects_before_storage(self):
        self.validator.side_effect = ValidationError("Invalid image")
        self.assertEqual(self.client.post(self.url, {"photo": upload()}).status_code, 400)
        self.storage.assert_not_called()

    def test_size_limit_rejects_stream_before_validator_or_disk(self):
        response = self.client.post(self.url, {"photo": upload(b"x" * (MAX_PHOTO_BYTES + 1))})
        self.assertEqual(response.status_code, 400)
        self.assertIn("5 MB", response.json()["error"])
        self.validator.assert_not_called()
        self.storage.assert_not_called()

    def test_exact_size_limit_uses_in_memory_file(self):
        response = self.client.post(self.url, {"photo": upload(b"x" * MAX_PHOTO_BYTES)})
        self.assertEqual(response.status_code, 200)
        file = self.validator.call_args.args[0]
        self.assertFalse(hasattr(file, "temporary_file_path"))

    def test_unauthenticated_and_csrf_requests_cannot_modify_photos(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"action": "remove"}).status_code, 302)
        secure_client = Client(enforce_csrf_checks=True)
        secure_client.force_login(self.user)
        self.assertEqual(secure_client.post(self.url, {"action": "remove"}).status_code, 403)
        self.storage.assert_not_called()

    def test_other_user_cannot_select_another_profiles_photo(self):
        self.client.post(self.url, {"photo": upload()})
        self.profile.refresh_from_db()
        key = self.profile.photo_reference
        other = get_user_model().objects.create_user(username="other@yale.edu")
        self.client.force_login(other)
        with mock.patch("core.photo_views.photo_storage.download") as download:
            response = self.client.get(self.url, {"object_key": key, "user": self.user.pk})
            self.assertEqual(response.status_code, 404)
            download.assert_not_called()
        self.client.post(self.url, {"action": "remove", "user": self.user.pk})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_reference, key)

    def test_photo_is_proxied_privately_without_exposing_credentials(self):
        self.client.post(self.url, {"photo": upload()})
        with mock.patch("core.photo_views.photo_storage.download", return_value=PNG):
            response = self.client.get(self.url)
        self.assertEqual(response.content, PNG)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("no-store", response["Cache-Control"])

    def test_missing_validator_fails_safely(self):
        self.validator.side_effect = StorageUnavailable("dependency missing")
        self.assertEqual(self.client.post(self.url, {"photo": upload()}).status_code, 503)
        self.storage.assert_not_called()


class PhotoBasicValidationTests(SimpleTestCase):
    def test_oversized_and_wrong_mime_rejected(self):
        for item in [upload(b"x" * (MAX_PHOTO_BYTES + 1)), upload(mime="text/html")]:
            with self.assertRaises(ValidationError):
                validate_photo(item)


@skipUnless(importlib.util.find_spec("PIL"), "Pillow must be installed to verify actual image decoding")
class PhotoImageValidationTests(SimpleTestCase):
    def make_image(self, format="PNG", size=(8, 8)):
        from PIL import Image
        stream = BytesIO()
        Image.new("RGB", size, "blue").save(stream, format=format)
        return stream.getvalue()

    def test_jpeg_and_png_are_decoded_and_sanitized(self):
        from PIL import Image
        for format, mime in [("JPEG", "image/jpeg"), ("PNG", "image/png")]:
            data, content_type = validate_photo(upload(self.make_image(format), mime))
            self.assertEqual(content_type, mime)
            Image.open(BytesIO(data)).verify()

    def test_forged_mime_corrupt_image_and_disallowed_format_rejected(self):
        for data in [b"<script>alert(1)</script>", self.make_image()[:30], self.make_image("GIF")]:
            with self.assertRaises(ValidationError):
                validate_photo(upload(data))

    def test_large_image_is_resized(self):
        from PIL import Image
        data, _ = validate_photo(upload(self.make_image(size=(2048, 1024))))
        self.assertEqual(Image.open(BytesIO(data)).size, (1024, 512))

    def test_pixel_bomb_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_photo(upload(self.make_image(size=(5001, 5000))))


@override_settings(SUPABASE_STORAGE_URL="https://example.supabase.co", SUPABASE_STORAGE_KEY="test-key", SUPABASE_PHOTO_BUCKET="profile-photos")
class StorageAdapterTests(SimpleTestCase):
    @mock.patch("core.photo_storage.build_opener")
    def test_upload_uses_private_server_auth_and_no_overwrites(self, opener):
        from core.photo_storage import upload as store
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{}'
        store("profiles/1/new.png", PNG, "image/png")
        req = opener.return_value.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://example.supabase.co/storage/v1/object/profile-photos/profiles/1/new.png")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(req.get_header("X-upsert"), "false")

    @override_settings(SUPABASE_STORAGE_KEY="")
    def test_no_storage_credentials_fail_closed(self):
        from core.photo_storage import upload as store
        with mock.patch("core.photo_storage.build_opener") as opener:
            with self.assertRaises(StorageUnavailable):
                store("photo.png", PNG, "image/png")
            opener.assert_not_called()

    def test_bucket_setup_refuses_public_or_unrestricted_buckets(self):
        from core.photo_storage import ensure_bucket
        with mock.patch("core.photo_storage.request", return_value=b'{"public":true}'):
            with self.assertRaises(StorageUnavailable):
                ensure_bucket()
