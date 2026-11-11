import re

from django.core import mail

FAKE_FIXED_CODE = "135790"  # tests never use the real grader code
STUDENT = "student@yale.edu"


def last_code():
    """The 6-digit code from the most recent email Django captured in memory."""
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


def send_code(client, email=STUDENT):
    return client.post("/login/", {"email": email})


def assert_error(test, response, text):
    """The screen was shown again (400) with an error containing `text`."""
    test.assertEqual(response.status_code, 400)
    test.assertIn(text, response.context["error"])
