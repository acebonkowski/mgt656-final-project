import re
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from abtest.models import Click, Impression

BUTTON_RE = re.compile(r'<button[^>]*\bid="abtest"[^>]*>(.*?)</button>', re.S)


def button_texts(response):
    return [text.strip() for text in BUTTON_RE.findall(response.content.decode())]


class PagePublicTests(TestCase):
    def setUp(self):
        self.url = reverse("abtest:page")

    def test_public_200_lists_member_nicknames_and_no_popup(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for nickname in settings.TEAM_MEMBER_NICKNAMES:
            self.assertContains(response, nickname)
        html = response.content.decode().lower()
        for marker in ("<dialog", "<script", "modal", "alert("):
            self.assertNotIn(marker, html)

    def test_exactly_one_server_rendered_button(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertEqual(html.count('id="abtest"'), 1)
        texts = button_texts(response)
        self.assertEqual(len(texts), 1)
        self.assertIn(texts[0], ("kudos", "thanks"))
        self.assertEqual(texts[0], self.client.session["abtest"]["variant"])
        self.assertNotIn("<script", html)

    def test_never_cached(self):
        for name in ("abtest:page", "abtest:stats"):
            response = self.client.get(reverse(name))
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("private", response["Cache-Control"])


class VariantAssignmentTests(TestCase):
    def setUp(self):
        self.url = reverse("abtest:page")

    def test_each_variant_can_be_assigned(self):
        for variant in ("kudos", "thanks"):
            with mock.patch("abtest.views.choose_variant", return_value=variant):
                response = Client().get(self.url)
            self.assertEqual(button_texts(response), [variant])

    def test_new_visitors_split_roughly_50_50(self):
        n = 400
        for _ in range(n):
            Client().get(self.url)
        kudos = Impression.objects.filter(variant="kudos").count()
        self.assertEqual(Impression.objects.count(), n)
        # 40-60% band: a fair coin falls outside it about 1 time in 10,000.
        self.assertTrue(0.40 * n <= kudos <= 0.60 * n, f"kudos={kudos} of {n}")

    def test_variant_sticks_on_reload_and_return(self):
        first = button_texts(self.client.get(self.url))
        for _ in range(3):
            self.assertEqual(button_texts(self.client.get(self.url)), first)


class CountingTests(TestCase):
    def setUp(self):
        self.url = reverse("abtest:page")
        self.click_url = reverse("abtest:click")

    def test_first_view_stores_one_impression_reloads_store_none(self):
        self.client.get(self.url)
        self.assertEqual(Impression.objects.count(), 1)
        self.assertIsNotNone(Impression.objects.get().created_at)
        self.client.get(self.url)
        self.client.get(self.url)
        self.assertEqual(Impression.objects.count(), 1)

    def test_one_click_stored_with_timestamp_repeats_ignored(self):
        self.client.get(self.url)
        self.client.post(self.click_url)
        self.assertEqual(Click.objects.count(), 1)
        self.assertIsNotNone(Click.objects.get().created_at)
        self.client.post(self.click_url)
        self.client.post(self.click_url)
        self.assertEqual(Click.objects.count(), 1)

    def test_click_redirect_adds_no_impression_and_keeps_variant(self):
        variant = button_texts(self.client.get(self.url))
        response = self.client.post(self.click_url, follow=True)
        self.assertEqual(response.redirect_chain, [(self.url, 302)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(button_texts(response), variant)
        self.assertEqual(Impression.objects.count(), 1)
        self.assertEqual(Click.objects.count(), 1)
        self.assertEqual(Click.objects.get().impression.variant, variant[0])

    def test_click_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.get(self.url)
        response = client.post(self.click_url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Click.objects.count(), 0)

    def test_click_with_csrf_token_from_the_form_is_counted(self):
        client = Client(enforce_csrf_checks=True)
        html = client.get(self.url).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
        response = client.post(self.click_url, {"csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Click.objects.count(), 1)

    def test_click_without_prior_visit_is_ignored(self):
        response = self.client.post(self.click_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Click.objects.count(), 0)
        self.assertEqual(Impression.objects.count(), 0)

    def test_get_on_click_url_not_allowed(self):
        self.assertEqual(self.client.get(self.click_url).status_code, 405)

    def test_deleted_impression_is_recorded_again_with_same_variant(self):
        variant = button_texts(self.client.get(self.url))
        Impression.objects.all().delete()
        self.assertEqual(button_texts(self.client.get(self.url)), variant)
        self.assertEqual(Impression.objects.count(), 1)
        self.assertEqual(Impression.objects.get().variant, variant[0])
