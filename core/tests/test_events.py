from decimal import Decimal
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from zoneinfo import ZoneInfo
from django.core.files.uploadedfile import SimpleUploadedFile

from core.forms import EventForm
from core.models import Event


class EventModelTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user(username="event-maker@yale.edu")
        self.start = timezone.now()
        self.end = self.start + timedelta(hours=2)

    def make_event(self, **overrides):
        values = {
            "image": "events/test.jpg",
            "name": "Yale Demo",
            "description": "A demo event",
            "category": Event.Category.MUSIC_PERFORMANCE,
            "start_at": self.start,
            "end_at": self.end,
            "location": "Yale Commons",
            "latitude": Decimal("41.308300"),
            "longitude": Decimal("-72.927900"),
            "price": Decimal("0.00"),
            "link": "https://example.com/event",
            "creator": self.creator,
        }
        values.update(overrides)
        return Event(**values)

    def test_valid_event_and_imported_event_defaults(self):
        event = self.make_event()
        event.full_clean()
        event.save()

        imported = self.make_event(
            name="Imported",
            creator=None,
            source="calendar",
            external_id="calendar-123",
        )
        imported.full_clean()
        imported.save()

        self.assertEqual(Event.objects.count(), 2)
        self.assertIsNone(imported.creator)
        self.assertEqual(imported.source, "calendar")
        self.assertEqual(imported.external_id, "calendar-123")
        self.assertEqual(str(event), "Yale Demo")

    def test_category_choices_are_exactly_the_twelve_issue_categories(self):
        expected = {
            "music_performance",
            "art_film_exhibits",
            "festivals_seasonal",
            "talks_panels",
            "workshops_skills",
            "career_networking",
            "social_community",
            "food_drink",
            "sports_outdoors_wellness",
            "service_civic",
            "faith_spirituality",
            "campus_admin",
        }
        labels = dict(Event.Category.choices)
        self.assertEqual(set(labels), expected)
        self.assertEqual(len(Event.Category.choices), 12)

    def test_name_description_and_location_length_limits(self):
        for field, value, limit in (
            ("name", "n" * 31, 30),
            ("description", "d" * 151, 150),
            ("location", "l" * 501, 500),
        ):
            with self.subTest(field=field):
                event = self.make_event(**{field: value})
                with self.assertRaises(ValidationError) as ctx:
                    event.full_clean()
                self.assertIn(field, ctx.exception.message_dict)
                self.assertIn(str(limit), str(ctx.exception.message_dict[field][0]))

    def test_price_must_not_be_negative(self):
        event = self.make_event(price=Decimal("-0.01"))
        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_end_must_be_after_start(self):
        for end in (self.start, self.start - timedelta(minutes=1)):
            with self.subTest(end=end):
                event = self.make_event(end_at=end)
                with self.assertRaises(ValidationError):
                    event.full_clean()

    def test_zero_price_is_valid_free_value_and_import_fields_are_optional(self):
        event = self.make_event(price=Decimal("0"))
        event.full_clean()
        event.save()
        self.assertEqual(event.price, Decimal("0"))
        self.assertEqual(event.source, "")
        self.assertEqual(event.external_id, "")

    def test_address_and_start_end_aliases_use_canonical_fields(self):
        event = self.make_event()
        event.address = "10 Hillhouse Avenue"
        event.start = self.start
        event.end = self.end
        self.assertEqual(event.location, "10 Hillhouse Avenue")
        self.assertEqual(event.start_at, self.start)
        self.assertEqual(event.end_at, self.end)


class EventFormTests(TestCase):
    def image_upload(self, data=None, mime="image/png"):
        if data is None:
            from PIL import Image
            stream = BytesIO()
            Image.new("RGB", (8, 8), "blue").save(stream, format="PNG")
            data = stream.getvalue()
        return SimpleUploadedFile("event.png", data, content_type=mime)

    def valid_data(self, **overrides):
        new_york_date = timezone.now().astimezone(ZoneInfo("America/New_York")).date()
        values = {
            "name": "Yale Event",
            "description": "An event description",
            "category": Event.Category.MUSIC_PERFORMANCE,
            "date": new_york_date.isoformat(),
            "start_time": "18:00",
            "end_time": "20:00",
            "location": "Yale Commons",
            "location_confirmed": "Yale Commons",
            "latitude": "41.308300",
            "longitude": "-72.927900",
            "price": "0",
            "link": "https://example.com/event",
        }
        values.update(overrides)
        return values

    def valid_form(self, **overrides):
        values = overrides.pop("data", {})
        data = self.valid_data(**values)
        return EventForm(data=data, files={"image": overrides.pop("image", self.image_upload())})

    def test_valid_form_saves_america_new_york_times_and_free_price(self):
        form = self.valid_form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price"], Decimal("0"))
        start = form.cleaned_data["start_at"]
        end = form.cleaned_data["end_at"]
        self.assertEqual(str(start.tzinfo), "America/New_York")
        self.assertGreater(end, start)

    def test_missing_fields_are_rejected(self):
        form = EventForm(data={})
        self.assertFalse(form.is_valid())
        for field in (
            "image", "name", "description", "category", "date", "start_time",
            "end_time", "location", "latitude", "longitude", "price", "link",
        ):
            self.assertIn(field, form.errors)

    def test_end_must_be_after_start(self):
        form = self.valid_form(data={"end_time": "18:00"})
        self.assertFalse(form.is_valid())
        self.assertIn("End time must be after start time.", form.non_field_errors())

    def test_negative_price_is_rejected(self):
        form = self.valid_form(data={"price": "-1"})
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_non_http_url_is_rejected(self):
        form = self.valid_form(data={"link": "ftp://example.com/event"})
        self.assertFalse(form.is_valid())
        self.assertIn("link", form.errors)

    def test_unconfirmed_address_is_rejected(self):
        form = self.valid_form(data={"location_confirmed": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("location", form.errors)

    def test_wrong_image_type_is_rejected(self):
        form = EventForm(
            data={**self.valid_data(), "image": self.image_upload(mime="text/html")},
            files={"image": self.image_upload(mime="text/html")},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_oversized_image_is_rejected(self):
        upload = SimpleUploadedFile(
            "event.png",
            b"x" * (5 * 1024 * 1024 + 1),
            content_type="image/png",
        )
        form = EventForm(data={**self.valid_data(), "image": upload}, files={"image": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_heic_image_is_converted_to_jpeg(self):
        from PIL import Image
        import pillow_heif

        source = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(source, format="PNG")
        heif_image = pillow_heif.from_pillow(Image.open(BytesIO(source.getvalue())))
        heic = BytesIO()
        heif_image.save(heic)
        upload = SimpleUploadedFile("event.heic", heic.getvalue(), content_type="image/heic")

        with mock.patch("core.photo_validation.MAX_PHOTO_BYTES", 5 * 1024 * 1024):
            from core.photo_validation import validate_event_photo
            data, content_type = validate_event_photo(upload)

        self.assertEqual(content_type, "image/jpeg")
        converted = Image.open(BytesIO(data))
        self.assertEqual(converted.format, "JPEG")

    def test_png_and_jpeg_are_accepted(self):
        from PIL import Image
        for image_format, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg")):
            stream = BytesIO()
            Image.new("RGB", (8, 8), "blue").save(stream, format=image_format)
            upload = SimpleUploadedFile(
                f"event.{image_format.lower()}",
                stream.getvalue(),
                content_type=mime,
            )
            form = EventForm(
                data=self.valid_data(),
                files={"image": upload},
            )
            self.assertTrue(form.is_valid(), form.errors)

    def test_edit_image_removal_requires_a_replacement_or_is_rejected(self):
        form = EventForm(
            data={**self.valid_data(), "remove_image": "1"},
            files={},
            existing_image="events/existing.jpg",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
