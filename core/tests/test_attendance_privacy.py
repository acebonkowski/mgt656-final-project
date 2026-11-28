"""
Attendance privacy (#41, #83): a user's "going" status is shown only to the group
they chose on the Settings page (friends, program, school or everyone, default
everyone). Enforced on the server through core.friends.attendance_visible_to().
"""

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from accounts.models import Profile
from core import friends
from core.models import Program, School
from core.tests.test_friend_profiles import befriend, going, make_event
from core.tests.test_friends import make_user

Choice = Profile.AttendanceVisibility


class AttendancePrivacyTests(TestCase):
    def setUp(self):
        som = School.objects.create(name="School of Management")
        law = School.objects.create(name="Law School")
        self.mba = Program.objects.create(school=som, name="MBA")
        self.emba = Program.objects.create(school=som, name="EMBA")
        self.jd = Program.objects.create(school=law, name="JD")
        self.owner = make_user("owner", name="Owner", program=self.mba)
        self.friend = make_user("friend", name="Friend", program=self.jd)
        self.classmate = make_user("classmate", name="Classmate", program=self.mba)
        self.schoolmate = make_user("schoolmate", name="Schoolmate", program=self.emba)
        self.stranger = make_user("stranger", name="Stranger", program=self.jd)
        self.no_program = make_user("noprog", name="No program")
        befriend(self.owner, self.friend)

    def choose(self, value):
        Profile.objects.filter(user=self.owner).update(attendance_visibility=value)

    def who_sees(self):
        others = [self.friend, self.classmate, self.schoolmate, self.stranger, self.no_program]
        return {u.profile.username for u in others if friends.attendance_visible_to(u, self.owner)}

    def test_new_accounts_default_to_everyone(self):
        self.assertEqual(Profile.objects.get(user=self.owner).attendance_visibility, "everyone")
        self.assertEqual(len(self.who_sees()), 5)

    def test_friends_only(self):
        self.choose(Choice.FRIENDS)
        self.assertEqual(self.who_sees(), {"friend"})

    def test_program_only_means_same_program(self):
        self.choose(Choice.PROGRAM)
        self.assertEqual(self.who_sees(), {"classmate"})

    def test_school_means_same_school(self):
        self.choose(Choice.SCHOOL)
        self.assertEqual(self.who_sees(), {"classmate", "schoolmate"})

    def test_owner_always_sees_own_and_anonymous_only_sees_everyone(self):
        self.choose(Choice.FRIENDS)
        self.assertTrue(friends.attendance_visible_to(self.owner, self.owner))
        self.assertFalse(friends.attendance_visible_to(AnonymousUser(), self.owner))
        self.choose(Choice.EVERYONE)
        self.assertTrue(friends.attendance_visible_to(AnonymousUser(), self.owner))

    def test_viewer_without_program_never_matches_a_group(self):
        self.owner.profile.program = None
        self.owner.profile.save()
        self.choose(Choice.PROGRAM)
        self.assertEqual(self.who_sees(), set())
        self.choose(Choice.SCHOOL)
        self.assertEqual(self.who_sees(), set())

    def test_queryset_form_matches_function_form(self):
        from django.contrib.auth import get_user_model
        for value in Choice.values:
            self.choose(value)
            for viewer in (self.friend, self.classmate, self.schoolmate, self.stranger):
                in_q = get_user_model().objects.filter(
                    friends.attendance_visible_q(viewer), pk=self.owner.pk).exists()
                self.assertEqual(in_q, friends.attendance_visible_to(viewer, self.owner), (value, viewer))


class ProfilePageEnforcementTests(TestCase):
    """The friend profile page (#97) hides going events from outside the chosen group."""

    def setUp(self):
        school = School.objects.create(name="School of Management")
        mba = Program.objects.create(school=school, name="MBA")
        jd = Program.objects.create(school=School.objects.create(name="Law"), name="JD")
        self.owner = make_user("owner", name="Owner", program=mba)
        self.friend = make_user("friend", name="Friend", program=jd)
        befriend(self.owner, self.friend)
        self.event = make_event("Jazz Night")
        going(self.owner, self.event)
        self.client.force_login(self.friend)

    def page(self):
        return self.client.get("/people/owner/")

    def test_friend_sees_events_when_everyone_or_friends(self):
        for value in (Choice.EVERYONE, Choice.FRIENDS):
            Profile.objects.filter(user=self.owner).update(attendance_visibility=value)
            self.assertContains(self.page(), "Jazz Night")

    def test_friend_outside_the_chosen_group_sees_nothing(self):
        for value in (Choice.PROGRAM, Choice.SCHOOL):
            Profile.objects.filter(user=self.owner).update(attendance_visibility=value)
            response = self.page()
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Jazz Night")
