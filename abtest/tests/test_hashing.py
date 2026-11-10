from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from abtest.hashing import nickname_hash


class NicknameHashTests(SimpleTestCase):
    def test_course_example_bright_forest(self):
        # printf %s bright-forest | shasum -> 211c220...
        self.assertEqual(nickname_hash("bright-forest"), "211c220")

    def test_does_not_hash_a_trailing_newline(self):
        # `echo` would give 1ea0cdf; we must match printf %s.
        self.assertNotEqual(nickname_hash("bright-forest"), "1ea0cdf")
        self.assertEqual(nickname_hash("bright-forest\n"), "211c220")

    def test_our_team_nickname(self):
        self.assertEqual(nickname_hash("holy-dew"), "e75d81f")

    def test_page_paths_come_from_the_team_nickname_setting(self):
        h = nickname_hash(settings.TEAM_NICKNAME)
        self.assertEqual(reverse("abtest:page"), f"/{h}")
        self.assertEqual(reverse("abtest:stats"), f"/{h}/stats")
