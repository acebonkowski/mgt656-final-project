"""
Event visibility (#41): the creator picks who can see an event, and the server
hides it everywhere else (404, so its existence isn't revealed).

Groups come from the creator's profile. "Friends" is stored but only the creator
sees it until #39 adds friendships. Attendance privacy waits on #83/#39/#85.
OpenRouter, the geocoder and photo storage are mocked.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Profile
from core.forms import EventForm
from core.models import Event, EventFavorite, Program, School
from core.tests.test_ai_search import CONFIGURED, model_output
from core.visibility import can_view, visible_events

E = Event.Visibility


def make_event(name="Secret Show", visibility=E.EVERYONE, creator=None, **fields):
    start = timezone.now() + timedelta(days=1)
    values = {
        "image": "events/1/test.jpg", "name": name, "description": "Hidden description",
        "category": "music_performance", "start_at": start,
        "end_at": start + timedelta(hours=2), "location": f"Place for {name}",
        "latitude": "41.308300", "longitude": "-72.927900", "price": "0",
        "link": "https://example.com/event", "creator": creator, "visibility": visibility,
    }
    values.update(fields)
    return Event.objects.create(**values)


class VisibilityTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="School One")
        cls.other_school = School.objects.create(name="School Two")
        cls.program = Program.objects.create(school=cls.school, name="Program A")
        cls.sibling_program = Program.objects.create(school=cls.school, name="Program B")
        cls.far_program = Program.objects.create(school=cls.other_school, name="Program C")
        cls.creator = cls.user("creator", cls.program)
        cls.same_program = cls.user("same-program", cls.program)
        cls.same_school = cls.user("same-school", cls.sibling_program)
        cls.outsider = cls.user("outsider", cls.far_program)
        cls.no_program = cls.user("no-program", None)

    @staticmethod
    def user(name, program):
        user = get_user_model().objects.create_user(username=f"{name}@yale.edu",
                                                    email=f"{name}@yale.edu")
        Profile.objects.create(user=user, username=f"u{user.pk}", onboarding_complete=True, program=program)
        return user

    def get_as(self, user, url, data=None):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        return self.client.get(url, data)

    def post_as(self, user, url, data=None):
        self.client.logout()
        self.client.force_login(user)
        return self.client.post(url, data or {})


class RuleTests(VisibilityTestCase):
    """Who may see an event, for each visibility."""

    def allowed(self, visibility):
        event = make_event(visibility=visibility, creator=self.creator)
        users = {"creator": self.creator, "same_program": self.same_program,
                 "same_school": self.same_school, "outsider": self.outsider,
                 "no_program": self.no_program}
        return {name for name, user in users.items() if can_view(user, event)}

    def test_everyone(self):
        self.assertEqual(self.allowed(E.EVERYONE), {
            "creator", "same_program", "same_school", "outsider", "no_program"})

    def test_school(self):
        self.assertEqual(self.allowed(E.SCHOOL), {"creator", "same_program", "same_school"})

    def test_program(self):
        self.assertEqual(self.allowed(E.PROGRAM), {"creator", "same_program"})

    def test_friends_is_the_creator_only_until_friendships_exist(self):
        self.assertEqual(self.allowed(E.FRIENDS), {"creator"})

    def test_logged_out_visitors_only_see_everyone(self):
        from django.contrib.auth.models import AnonymousUser
        public = make_event("Public")
        private = make_event("Private", E.SCHOOL, self.creator)
        ids = set(visible_events(Event.objects.all(), AnonymousUser()).values_list("pk", flat=True))
        self.assertEqual(ids, {public.pk})
        self.assertNotIn(private.pk, ids)

    def test_events_without_a_creator_are_always_visible(self):
        event = make_event("Imported", E.PROGRAM, None)
        self.assertTrue(can_view(self.outsider, event))

    def test_a_creator_with_no_program_never_matches_a_group(self):
        event = make_event("Orphan", E.SCHOOL, self.no_program)
        self.assertFalse(can_view(self.no_program, make_event("x", E.SCHOOL, self.creator)))  # viewer has none
        self.assertFalse(can_view(self.outsider, event))
        self.assertTrue(can_view(self.no_program, event))  # their own event

    def test_group_follows_the_creators_current_program(self):
        event = make_event(visibility=E.PROGRAM, creator=self.creator)
        self.assertFalse(can_view(self.outsider, event))
        Profile.objects.filter(user=self.creator).update(program=self.far_program)
        self.assertTrue(can_view(self.outsider, event))


class DefaultTests(VisibilityTestCase):
    def test_new_events_default_to_everyone(self):
        start = timezone.now() + timedelta(days=1)
        event = Event.objects.create(
            image="x", name="n", description="d", category="music_performance",
            start_at=start, end_at=start + timedelta(hours=1), location="l",
            latitude="41.3", longitude="-72.9", price="0")
        self.assertEqual(event.visibility, E.EVERYONE)

    def form(self, **extra):
        data = {"name": "Party", "description": "Fun", "category": "music_performance",
                "date": "2030-01-02", "start_time": "18:00", "end_time": "20:00",
                "location": "Yale", "location_confirmed": "Yale", "latitude": "41.3",
                "longitude": "-72.9", "price": "0", "ai_image": "", **extra}
        form = EventForm(data, creator=self.creator)
        form.fields["image"].required = False
        return form

    def test_the_form_defaults_to_everyone_when_the_field_is_missing(self):
        form = self.form()
        form.is_valid()
        self.assertEqual(form.cleaned_data["visibility"], E.EVERYONE)

    def test_friends_is_not_offered_in_the_form(self):
        self.assertNotIn(E.FRIENDS, [value for value, _ in EventForm().fields["visibility"].choices])
        form = self.form(visibility=E.FRIENDS)
        form.is_valid()
        self.assertIn("visibility", form.errors)

    def test_school_and_program_need_a_program_on_the_profile(self):
        form = EventForm(self.form(visibility=E.PROGRAM).data, creator=self.no_program)
        form.is_valid()
        self.assertIn("visibility", form.errors)
        form = self.form(visibility=E.PROGRAM)
        form.is_valid()
        self.assertNotIn("visibility", form.errors)

    def test_editing_without_the_field_keeps_a_friends_event_private(self):
        form = EventForm(self.form().data, creator=self.creator, existing_visibility=E.FRIENDS)
        form.is_valid()
        self.assertEqual(form.cleaned_data["visibility"], E.FRIENDS)


class FormPageTests(VisibilityTestCase):
    def test_create_and_edit_forms_show_the_choice(self):
        event = make_event("Mine", E.PROGRAM, self.creator)
        self.client.force_login(self.creator)
        create = self.client.get("/map/").content.decode()
        self.assertIn('name="visibility"', create)
        self.assertIn("My school", create)
        # Check the option, not the text: the profile menu also says "Friends" (#81).
        self.assertNotIn('<option value="friends"', create)
        edit = self.client.get(f"/events/{event.pk}/edit/")
        self.assertEqual(edit.context["event_form"].initial["visibility"], E.PROGRAM)


class EnforcementTests(VisibilityTestCase):
    def setUp(self):
        self.event = make_event(visibility=E.PROGRAM, creator=self.creator)
        self.page = f"/events/{self.event.pk}/"

    def test_page_popup_and_calendar_404_for_outsiders_200_for_the_group(self):
        for suffix in ("", "popup/", "calendar.ics"):
            url = self.page + suffix
            for user in (self.same_school, self.outsider, self.no_program):
                self.assertEqual(self.get_as(user, url).status_code, 404, (suffix, user))
            for user in (self.creator, self.same_program):
                self.assertEqual(self.get_as(user, url).status_code, 200, (suffix, user))

    def test_a_hidden_event_looks_the_same_as_a_missing_one(self):
        missing = self.get_as(self.outsider, "/events/999999/")
        hidden = self.get_as(self.outsider, self.page)
        self.assertEqual(missing.status_code, hidden.status_code)

    def test_map_pins(self):
        def pins(user):
            return [e["name"] for e in self.get_as(user, "/map/").context["map_config"]["events"]]

        self.assertEqual(pins(self.outsider), [])
        self.assertEqual(pins(self.same_school), [])
        self.assertEqual(pins(self.same_program), ["Secret Show"])
        self.assertEqual(pins(self.creator), ["Secret Show"])

    def test_search_results(self):
        def names(user):
            return [e["name"] for e in self.get_as(user, "/events/search/").json()["events"]]

        self.assertEqual(names(self.outsider), [])
        self.assertEqual(names(self.same_program), ["Secret Show"])
        self.assertEqual(self.get_as(self.outsider, "/events/search/?q=secret").json()["count"], 0)

    @override_settings(**CONFIGURED)
    def test_ai_search_results(self):
        with mock.patch("core.ai_search.llm.chat_json") as chat, \
                mock.patch("core.ai_search.geocoding.search", return_value=[]):
            chat.return_value = model_output(q="secret")
            self.client.force_login(self.outsider)
            self.assertEqual(self.client.post("/events/search/ai/", {"message": "secret"}).json()["events"], [])
            self.client.force_login(self.same_program)
            events = self.client.post("/events/search/ai/", {"message": "secret"}).json()["events"]
            self.assertEqual([e["name"] for e in events], ["Secret Show"])

    def test_the_school_level_reaches_the_whole_school(self):
        make_event("School Mixer", E.SCHOOL, self.creator, location="Elsewhere")
        def names(user):
            return [e["name"] for e in self.get_as(user, "/events/search/").json()["events"]]

        self.assertIn("School Mixer", names(self.same_school))
        self.assertNotIn("School Mixer", names(self.outsider))

    def test_going_and_favorite_404_for_outsiders_and_save_nothing(self):
        self.assertEqual(self.post_as(self.outsider, self.page + "going/", {"status": "going"}).status_code, 404)
        self.assertEqual(self.post_as(self.outsider, self.page + "favorite/", {"favorited": "true"}).status_code, 404)
        self.assertFalse(self.event.attendances.exists())
        self.assertFalse(EventFavorite.objects.exists())
        self.assertEqual(self.post_as(self.same_program, self.page + "going/", {"status": "going"}).status_code, 200)

    def test_my_events_leave_out_events_that_became_hidden(self):
        EventFavorite.objects.create(user=self.outsider, event=self.event)
        self.event.attendances.create(user=self.outsider, status="going")
        for url in ("/my-events/favorites/", "/my-events/upcoming/"):
            self.assertEqual(list(self.get_as(self.outsider, url).context["events"]), [], url)

    def test_edit_and_delete_404_for_outsiders_not_403(self):
        self.assertEqual(self.get_as(self.outsider, self.page + "edit/").status_code, 404)
        self.assertEqual(self.post_as(self.outsider, self.page + "delete/").status_code, 404)
        self.assertEqual(self.get_as(self.same_program, self.page + "edit/").status_code, 403)
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_the_duplicate_check_does_not_name_a_hidden_event(self):
        from zoneinfo import ZoneInfo
        at = (timezone.now() + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
        event = make_event("Dup", E.PROGRAM, self.creator, start_at=at, end_at=at + timedelta(hours=2))
        query = {"location": event.location, "date": "", "start_time": "", "end_time": ""}
        start = event.start_at.astimezone(ZoneInfo("America/New_York"))
        end = event.end_at.astimezone(ZoneInfo("America/New_York"))
        query.update(date=start.strftime("%Y-%m-%d"), start_time=start.strftime("%H:%M"),
                     end_time=end.strftime("%H:%M"), end_date=end.strftime("%Y-%m-%d"))
        found = self.get_as(self.same_program, "/map/duplicate/", query).json()["match"]
        self.assertEqual(found["id"], event.pk)
        self.assertIsNone(self.get_as(self.outsider, "/map/duplicate/", query).json()["match"])

    def test_the_image_is_hidden_with_the_event(self):
        url = f"/event-photo/{self.event.image}"
        with mock.patch("core.views.photo_storage.download", return_value=b"img"):
            self.assertEqual(self.get_as(self.outsider, url).status_code, 404)
            self.assertEqual(self.get_as(None, url).status_code, 404)
            self.assertEqual(self.get_as(self.same_program, url).status_code, 200)


class PublicShareLinkTests(VisibilityTestCase):
    """The #32 share link: public events stay open; others show only a login page."""

    def test_public_events_still_open_logged_out(self):
        event = make_event("Open Mic")
        response = self.get_as(None, f"/events/{event.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open Mic")
        self.assertContains(response, 'id="join-cta"')
        self.assertEqual(self.get_as(None, f"/events/{event.pk}/calendar.ics").status_code, 200)

    def test_non_public_events_show_only_the_private_page_logged_out(self):
        for visibility in (E.SCHOOL, E.PROGRAM, E.FRIENDS):
            event = make_event("Secret Show", visibility, self.creator, location=f"Spot {visibility}")
            response = self.get_as(None, f"/events/{event.pk}/")
            self.assertEqual(response.status_code, 403)
            self.assertContains(response, "This event is private, log in to see it", status_code=403)
            html = response.content.decode()
            for detail in ("Secret Show", "Hidden description", event.location, "example.com",
                           event.image, "share-event", "Save to Calendar"):
                self.assertNotIn(detail, html, (visibility, detail))
            self.assertIn(f"/login/?next=%2Fevents%2F{event.pk}%2F", html)

    def test_other_urls_for_a_private_event_are_404_logged_out(self):
        event = make_event(visibility=E.SCHOOL, creator=self.creator)
        for suffix in ("popup/", "calendar.ics"):
            self.assertEqual(self.get_as(None, f"/events/{event.pk}/{suffix}").status_code, 404)

    def test_a_missing_event_is_still_404_logged_out(self):
        self.assertEqual(self.get_as(None, "/events/999999/").status_code, 404)

    def test_after_login_the_normal_check_applies(self):
        event = make_event(visibility=E.PROGRAM, creator=self.creator)
        self.assertEqual(self.get_as(None, f"/events/{event.pk}/").status_code, 403)
        # The login link returns to the event page, where the usual rule decides.
        self.assertEqual(self.get_as(self.same_program, f"/events/{event.pk}/").status_code, 200)
        self.assertEqual(self.get_as(self.outsider, f"/events/{event.pk}/").status_code, 404)
