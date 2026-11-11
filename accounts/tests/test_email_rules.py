from django.test import SimpleTestCase

from accounts.otp import EmailNotAllowed, check_email


class YaleEmailRuleTests(SimpleTestCase):
    def test_accepts_yale_and_its_subdomains_and_normalizes(self):
        self.assertEqual(check_email("student@yale.edu"), "student@yale.edu")
        self.assertEqual(check_email("  Student@SOM.Yale.EDU "), "student@som.yale.edu")

    def test_rejects_other_and_look_alike_domains(self):
        for email in ["a@gmail.com", "a@fakeyale.edu", "a@yale.edu.evil.com",
                      "a@yale.com", "a@notyale.edu"]:
            with self.subTest(email=email), self.assertRaisesMessage(
                EmailNotAllowed, "Only yale.edu email addresses are accepted."
            ):
                check_email(email)

    def test_rejects_empty_and_malformed(self):
        with self.assertRaisesMessage(EmailNotAllowed, "Please enter your Yale email address."):
            check_email("   ")
        for email in ["yale.edu", "a@", "@yale.edu", "a b@yale.edu"]:
            with self.subTest(email=email), self.assertRaisesMessage(
                EmailNotAllowed, "Please enter a valid email address."
            ):
                check_email(email)
