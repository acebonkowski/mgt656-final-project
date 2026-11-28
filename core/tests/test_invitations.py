"""Invitations: send an event to a friend, answer on the map, View All (#86)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core import invitations
from core.models import Event, EventAttendance, EventInvitation, FriendRequest, Program, School
from core.tests.test_friend_profiles import befriend, make_event
from core.tests.test_friends import T0, at, make_user


class InvitationTestCase(TestCase):
    def setUp(self):
        school = School.objects.create(name="School of Management")
        self.mba = Program.objects.create(school=school, name="MBA")
        self.jd = Program.objects.create(school=School.objects.create(name="Law"), name="JD")
        self.alex = make_user("alex", name="Alex", program=self.mba)
        self.bea = make_user("bea", name="Bea", program=self.mba)
        self.cy = make_user("cy", name="Cy", program=self.jd)
        self.eve = make_user("eve", name="Eve", program=self.mba)  # not a friend
        befriend(self.alex, self.bea)
        befriend(self.cy, self.alex)
        self.event = make_event("Jazz Night")
        self.client.force_login(self.alex)

    def send(self, recipients, event=None, note=""):
        event = event or self.event
        return self.client.post(f"/events/{event.pk}/invitations/", {
            "recipients": [user.pk for user in recipients], "note": note,
        })

    def invitation(self, recipient=None, event=None):
        return EventInvitation.objects.get(sender=self.alex, recipient=recipient or self.bea,
                                           event=event or self.event)

    def reply(self, invitation, status, message=""):
        return self.client.post(f"/invitations/{invitation.pk}/reply/",
                                {"status": status, "message": message})

    def box(self):
        return self.client.get("/map/").context["invitation_items"]


class SendTests(InvitationTestCase):
    def test_a_sent_event_shows_in_the_friends_invitations_box(self):
        response = self.send([self.bea], note="Want to go together?")
        self.assertRedirects(response, f"/events/{self.event.pk}/", fetch_redirect_response=False)
        self.assertContains(self.client.get(response.url), "Sent to Bea.")
        self.client.force_login(self.bea)
        items = self.box()
        self.assertEqual([item["event"] for item in items], [self.event])
        html = self.client.get("/map/").content.decode()
        self.assertIn("From Alex: “Want to go together?”", html)
        self.assertIn('aria-label="1 unanswered invitations"', html)

    def test_several_friends_at_once(self):
        self.send([self.bea, self.cy])
        self.assertEqual(EventInvitation.objects.count(), 2)

    def test_non_friends_are_refused_and_nothing_is_saved(self):
        self.send([self.bea, self.eve])
        self.assertEqual(EventInvitation.objects.count(), 0)
        FriendRequest.objects.create(sender=self.alex, recipient=self.eve, last_sent_at=timezone.now())
        self.send([self.eve])  # pending request: still not a friend
        self.assertEqual(EventInvitation.objects.count(), 0)

    def test_a_friend_who_cannot_see_the_event_is_refused(self):
        mba_only = make_event("MBA Mixer", creator=self.bea, visibility=Event.Visibility.PROGRAM)
        response = self.send([self.cy], event=mba_only)  # Cy is in the JD program
        self.assertEqual(EventInvitation.objects.count(), 0)
        self.assertContains(self.client.get(response.url), "They can&#x27;t see this event.")

    def test_an_ended_event_is_refused(self):
        start = timezone.now() - timedelta(days=1)
        ended = make_event("Old Show", start_at=start, end_at=start + timedelta(hours=2))
        self.send([self.bea], event=ended)
        self.assertEqual(EventInvitation.objects.count(), 0)

    def test_the_host_cannot_be_invited_and_you_cannot_invite_yourself(self):
        hosted = make_event("Bea's Party", creator=self.bea)
        self.send([self.bea], event=hosted)
        self.send([self.alex])
        self.assertEqual(EventInvitation.objects.count(), 0)

    def test_an_event_hidden_from_the_sender_is_a_404(self):
        hidden = make_event("Law Only", creator=self.cy, visibility=Event.Visibility.PROGRAM)
        self.assertEqual(self.send([self.bea], event=hidden).status_code, 404)

    def test_sending_twice_is_refused(self):
        self.send([self.bea])
        self.send([self.bea])
        self.assertEqual(EventInvitation.objects.count(), 1)

    def test_the_picker_lists_only_friends_who_may_get_the_event(self):
        self.send([self.bea])
        response = self.client.get(f"/events/{self.event.pk}/")
        self.assertEqual([p["name"] for p in response.context["invite_friends"]], ["Cy"])
        self.assertContains(response, "Send to Friend")
        popup = self.client.get(f"/events/{self.event.pk}/popup/")
        self.assertContains(popup, "Send to Friend")

    def test_unknown_user_ids_are_refused(self):
        self.client.post(f"/events/{self.event.pk}/invitations/", {"recipients": [99999]})
        self.assertEqual(EventInvitation.objects.count(), 0)


class ReplyTests(InvitationTestCase):
    def setUp(self):
        super().setUp()
        self.send([self.bea], note="Come!")
        self.invite = self.invitation()
        self.client.force_login(self.bea)

    def test_the_reply_and_message_are_visible_to_the_sender(self):
        self.reply(self.invite, "maybe", "if I finish my problem set")
        self.client.force_login(self.alex)
        response = self.client.get("/invitations/")
        [group] = response.context["groups"]
        [item] = group["items"]
        self.assertEqual((item["status"], item["status_label"]), ("maybe", "Maybe"))
        self.assertContains(response, "“if I finish my problem set”")

    def test_the_reply_is_the_event_page_going_status(self):
        self.reply(self.invite, "maybe")
        response = self.client.get(f"/events/{self.event.pk}/")
        self.assertEqual(response.context["going_status"], "maybe")
        self.assertEqual(EventAttendance.objects.get(user=self.bea, event=self.event).status, "maybe")

    def test_add_to_calendar_is_offered_after_going(self):
        html = self.client.get("/map/").content.decode()
        self.assertNotIn(f'id="add-to-calendar-{self.invite.pk}"', html)
        self.reply(self.invite, "going")
        html = self.client.get("/map/").content.decode()
        self.assertIn(f'id="add-to-calendar-{self.invite.pk}"', html)
        self.assertIn(f'href="/events/{self.event.pk}/calendar.ics"', html)
        ics = self.client.get(f"/events/{self.event.pk}/calendar.ics")
        self.assertEqual(ics.status_code, 200)
        self.assertIn(b"BEGIN:VCALENDAR", ics.content)

    def test_maybe_does_not_offer_add_to_calendar(self):
        self.reply(self.invite, "maybe")
        self.assertNotIn(f'id="add-to-calendar-{self.invite.pk}"', self.client.get("/map/").content.decode())

    def test_a_later_change_on_the_event_page_shows_in_view_all(self):
        self.reply(self.invite, "going")
        self.client.post(f"/events/{self.event.pk}/going/", {"status": "not_going"})
        self.client.force_login(self.alex)
        [item] = self.client.get("/invitations/").context["groups"][0]["items"]
        self.assertEqual(item["status_label"], "Not going")

    def test_only_the_recipient_can_reply(self):
        for user in (self.alex, self.cy):
            self.client.force_login(user)
            self.assertEqual(self.reply(self.invite, "going").status_code, 404)
        self.assertFalse(EventAttendance.objects.exists())

    def test_an_unknown_status_is_refused(self):
        self.reply(self.invite, "yes please")
        self.assertFalse(EventAttendance.objects.exists())

    def test_long_messages_are_cut_to_140_characters(self):
        self.reply(self.invite, "going", "x" * 300)
        self.invite.refresh_from_db()
        self.assertEqual(len(self.invite.reply_message), 140)

    def test_replies_stop_when_the_event_ends(self):
        Event.objects.filter(pk=self.event.pk).update(
            start_at=timezone.now() - timedelta(hours=3), end_at=timezone.now() - timedelta(hours=1))
        self.reply(self.invite, "going")
        self.assertFalse(EventAttendance.objects.exists())

    def test_ended_events_leave_the_box(self):
        self.assertEqual(len(self.box()), 1)
        Event.objects.filter(pk=self.event.pk).update(
            start_at=timezone.now() - timedelta(hours=3), end_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.box(), [])

    def test_events_that_became_hidden_leave_the_box(self):
        Event.objects.filter(pk=self.event.pk).update(creator=self.cy, visibility=Event.Visibility.PROGRAM)
        self.assertEqual(self.box(), [])  # Bea is MBA, the event is now JD-only
        self.assertEqual(self.reply(self.invite, "going").status_code, 404)


class ViewAllTests(InvitationTestCase):
    def test_statuses_are_grouped_by_event(self):
        later = make_event("Late Show", days_ahead=3)
        self.send([self.bea, self.cy])
        self.send([self.bea], event=later)
        EventAttendance.objects.create(user=self.cy, event=self.event, status="going")
        response = self.client.get("/invitations/")
        groups = response.context["groups"]
        self.assertEqual([g["event"].name for g in groups], ["Jazz Night", "Late Show"])
        self.assertEqual([(i["person"]["name"], i["status_label"]) for i in groups[0]["items"]],
                         [("Bea", "No answer yet"), ("Cy", "Going")])
        self.assertEqual([i["person"]["name"] for i in groups[1]["items"]], ["Bea"])

    def test_the_box_links_to_view_all(self):
        self.assertContains(self.client.get("/map/"), 'href="/invitations/"')

    def test_only_your_own_sent_invitations_are_listed(self):
        self.send([self.bea])
        self.client.force_login(self.bea)
        self.assertEqual(self.client.get("/invitations/").context["groups"], [])


class ResendTests(InvitationTestCase):
    def setUp(self):
        super().setUp()
        with at(T0):
            self.event = make_event("Far Show", start_at=T0 + timedelta(days=30),
                                    end_at=T0 + timedelta(days=30, hours=2))
            self.send([self.bea], event=self.event)
        self.invite = self.invitation(event=self.event)

    def resend(self, moment):
        with at(moment):
            return self.client.post(f"/invitations/{self.invite.pk}/resend/")

    def test_within_24h_it_is_refused(self):
        self.resend(T0 + timedelta(hours=23))
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.resend_count, 0)

    def test_at_24h_it_is_sent_again_and_a_third_resend_is_refused(self):
        self.resend(T0 + timedelta(hours=24))
        self.resend(T0 + timedelta(hours=48))
        self.resend(T0 + timedelta(hours=72))
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.resend_count, 2)
        self.assertEqual(self.invite.last_sent_at, T0 + timedelta(hours=48))

    def test_answered_invitations_cannot_be_resent(self):
        EventAttendance.objects.create(user=self.bea, event=self.event, status="maybe")
        self.resend(T0 + timedelta(hours=24))
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.resend_count, 0)

    def test_only_the_sender_can_resend(self):
        self.client.force_login(self.bea)
        self.resend(T0 + timedelta(hours=24))
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.resend_count, 0)

    def test_a_resend_moves_it_to_the_top_of_the_box(self):
        with at(T0 + timedelta(hours=1)):
            self.client.force_login(self.cy)
            befriend(self.cy, self.bea)
            other = make_event("Other Show", start_at=T0 + timedelta(days=20),
                               end_at=T0 + timedelta(days=20, hours=2))
            self.send([self.bea], event=other)
        self.client.force_login(self.alex)
        self.resend(T0 + timedelta(hours=24))
        with at(T0 + timedelta(hours=25)):
            items = invitations.inbox(self.bea)
        self.assertEqual([item.event.name for item in items], ["Far Show", "Other Show"])


class AccessTests(InvitationTestCase):
    def test_logged_out_visitors_are_sent_to_login(self):
        self.client.logout()
        for url in (f"/events/{self.event.pk}/invitations/", "/invitations/1/reply/",
                    "/invitations/1/resend/"):
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("/login/", response.url)
        self.assertIn("/login/", self.client.get("/invitations/").url)
        self.assertNotContains(self.client.get(f"/events/{self.event.pk}/"), "Send to Friend")

    def test_the_database_refuses_an_invitation_to_yourself(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            EventInvitation.objects.create(sender=self.alex, recipient=self.alex, event=self.event,
                                           last_sent_at=timezone.now())
