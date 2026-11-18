"""AI usage limits (#36). Uses a fixed clock; no external calls."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core import ai_limits
from core.models import AIUsage

NY = ZoneInfo("America/New_York")
NOON = datetime(2026, 11, 18, 12, 0, tzinfo=NY)
SEARCH, IMAGE = AIUsage.Kind.SEARCH, AIUsage.Kind.IMAGE_SEARCH
LIMITS = dict(AI_SEARCH_DAILY_LIMIT=15, AI_SEARCH_PER_MINUTE_LIMIT=3,
              AI_IMAGE_SEARCH_DAILY_LIMIT=3, AI_GLOBAL_DAILY_LIMIT=200)


def use(user, n, at, kind=SEARCH):
    for i in range(n):
        AIUsage.objects.create(user=user, kind=kind, created_at=at + timedelta(seconds=i))


@override_settings(**LIMITS)
class AiLimitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="student@yale.edu",
                                                         email="student@yale.edu")

    def test_reserve_records_the_call(self):
        ai_limits.reserve(self.user, SEARCH, now=NOON)
        usage = AIUsage.objects.get()
        self.assertEqual((usage.user, usage.kind, usage.created_at), (self.user, SEARCH, NOON))

    def test_three_per_minute(self):
        use(self.user, 3, NOON - timedelta(seconds=30))
        with self.assertRaisesMessage(ai_limits.LimitReached, "Wait a minute"):
            ai_limits.check(self.user, SEARCH, now=NOON)
        ai_limits.check(self.user, SEARCH, now=NOON + timedelta(minutes=1))  # allowed again

    def test_fifteen_per_day(self):
        use(self.user, 15, NOON - timedelta(hours=3))
        with self.assertRaisesMessage(ai_limits.LimitReached, "today's 15 AI searches"):
            ai_limits.check(self.user, SEARCH, now=NOON)

    def test_image_searches_count_towards_the_daily_total(self):
        use(self.user, 14, NOON - timedelta(hours=3))
        use(self.user, 1, NOON - timedelta(hours=2), kind=IMAGE)
        with self.assertRaises(ai_limits.LimitReached):
            ai_limits.check(self.user, SEARCH, now=NOON)

    def test_three_image_searches_per_day(self):
        use(self.user, 3, NOON - timedelta(hours=3), kind=IMAGE)
        with self.assertRaisesMessage(ai_limits.LimitReached, "today's 3 image searches"):
            ai_limits.check(self.user, IMAGE, now=NOON)
        ai_limits.check(self.user, SEARCH, now=NOON)  # typing still works

    def test_day_resets_at_midnight_new_york(self):
        use(self.user, 15, datetime(2026, 11, 18, 23, 0, tzinfo=NY))
        with self.assertRaises(ai_limits.LimitReached):
            ai_limits.check(self.user, SEARCH, now=datetime(2026, 11, 18, 23, 59, tzinfo=NY))
        ai_limits.check(self.user, SEARCH, now=datetime(2026, 11, 19, 0, 1, tzinfo=NY))

    def test_other_users_do_not_count(self):
        other = get_user_model().objects.create_user(username="other@yale.edu")
        use(other, 15, NOON - timedelta(hours=3))
        ai_limits.check(self.user, SEARCH, now=NOON)

    def test_global_daily_cap_applies_to_everyone(self):
        other = get_user_model().objects.create_user(username="other@yale.edu")
        with override_settings(AI_GLOBAL_DAILY_LIMIT=5):
            use(other, 5, NOON - timedelta(hours=1))
            with self.assertRaisesMessage(ai_limits.LimitReached, "whole app"):
                ai_limits.check(self.user, SEARCH, now=NOON)
            grader = get_user_model().objects.create_user(
                username=settings.GRADER_MEMBER_EMAIL, email=settings.GRADER_MEMBER_EMAIL)
            with self.assertRaises(ai_limits.LimitReached):
                ai_limits.check(grader, SEARCH, now=NOON)

    def test_graders_and_staff_skip_per_user_limits(self):
        grader = get_user_model().objects.create_user(
            username=settings.GRADER_MEMBER_EMAIL, email=settings.GRADER_MEMBER_EMAIL)
        staff = get_user_model().objects.create_user(username="staff@yale.edu", is_staff=True)
        for user in (grader, staff):
            use(user, 20, NOON - timedelta(seconds=40))
            use(user, 5, NOON - timedelta(seconds=20), kind=IMAGE)
            ai_limits.check(user, IMAGE, now=NOON)
            self.assertTrue(ai_limits.is_exempt(user))
        self.assertFalse(ai_limits.is_exempt(self.user))

    def test_limits_come_from_settings(self):
        use(self.user, 2, NOON - timedelta(hours=1))
        with override_settings(AI_SEARCH_DAILY_LIMIT=2):
            with self.assertRaises(ai_limits.LimitReached):
                ai_limits.check(self.user, SEARCH, now=NOON)
