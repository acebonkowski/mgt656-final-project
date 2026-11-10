from unittest import mock

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from abtest.models import Click, Impression
from abtest.views import preferred_variant


def make(variant, impressions, clicks):
    for i in range(impressions):
        imp = Impression.objects.create(variant=variant)
        if i < clicks:
            Click.objects.create(impression=imp)


def counts(ki, kc, ti, tc):
    return {"kudos": {"impressions": ki, "clicks": kc}, "thanks": {"impressions": ti, "clicks": tc}}


class PreferredRuleTests(SimpleTestCase):
    def test_no_data_is_kudos(self):
        self.assertEqual(preferred_variant(counts(0, 0, 0, 0)), "kudos")

    def test_equal_rates_is_kudos(self):
        self.assertEqual(preferred_variant(counts(10, 3, 20, 6)), "kudos")

    def test_higher_rate_wins_not_higher_count(self):
        # thanks: 5/10 = 0.5 beats kudos: 30/100 = 0.3 despite fewer clicks.
        self.assertEqual(preferred_variant(counts(100, 30, 10, 5)), "thanks")
        self.assertEqual(preferred_variant(counts(10, 5, 100, 30)), "kudos")

    def test_variant_with_no_impressions_has_rate_zero(self):
        self.assertEqual(preferred_variant(counts(0, 0, 5, 1)), "thanks")
        self.assertEqual(preferred_variant(counts(5, 1, 0, 0)), "kudos")
        self.assertEqual(preferred_variant(counts(0, 0, 5, 0)), "kudos")


class StatsEndpointTests(TestCase):
    def setUp(self):
        self.url = reverse("abtest:stats")

    def test_public_json_with_no_data(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {
            "preferred": "kudos",
            "kudos": {"impressions": 0, "clicks": 0},
            "thanks": {"impressions": 0, "clicks": 0},
        })

    def test_counts_and_preferred_from_database(self):
        make("kudos", 10, 2)
        make("thanks", 8, 4)
        self.assertEqual(self.client.get(self.url).json(), {
            "preferred": "thanks",
            "kudos": {"impressions": 10, "clicks": 2},
            "thanks": {"impressions": 8, "clicks": 4},
        })

    def test_computed_live_on_each_request(self):
        make("kudos", 4, 1)
        make("thanks", 4, 2)
        self.assertEqual(self.client.get(self.url).json()["preferred"], "thanks")
        make("kudos", 4, 4)  # kudos now 5/8 vs thanks 2/4
        self.assertEqual(self.client.get(self.url).json()["preferred"], "kudos")

    def test_tie_from_database_is_kudos(self):
        make("kudos", 4, 2)
        make("thanks", 6, 3)
        self.assertEqual(self.client.get(self.url).json()["preferred"], "kudos")

    def test_end_to_end_visits_are_counted(self):
        page, click = reverse("abtest:page"), reverse("abtest:click")
        for variant, clicked in [("thanks", True), ("thanks", False), ("kudos", False), ("kudos", False)]:
            c = Client()
            with mock.patch("abtest.views.choose_variant", return_value=variant):
                c.get(page)
            if clicked:
                c.post(click, follow=True)
        data = self.client.get(self.url).json()
        self.assertEqual(data["preferred"], "thanks")
        self.assertEqual(data["thanks"], {"impressions": 2, "clicks": 1})
        self.assertEqual(data["kudos"], {"impressions": 2, "clicks": 0})
