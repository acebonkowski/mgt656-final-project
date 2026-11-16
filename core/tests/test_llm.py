"""OpenRouter wrapper tests. The real API is never called: the OpenAI client
is replaced with a mock in every test."""

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings
from openai import OpenAIError

from core import llm

CONFIGURED = dict(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="test/model")


def fake_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@override_settings(**CONFIGURED)
class ChatTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch("core.llm.OpenAI")
        self.openai_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.create = self.openai_cls.return_value.chat.completions.create

    def test_returns_reply_and_uses_openrouter(self):
        self.create.return_value = fake_response("Hello!")
        self.assertEqual(llm.chat([{"role": "user", "content": "Hi"}], max_tokens=16), "Hello!")
        kwargs = self.openai_cls.call_args.kwargs
        self.assertEqual(kwargs["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(kwargs["api_key"], "fake-key")
        self.assertEqual(self.create.call_args.kwargs["model"], "test/model")
        self.assertEqual(self.create.call_args.kwargs["max_tokens"], 16)

    def test_provider_error_becomes_llm_unavailable(self):
        self.create.side_effect = OpenAIError("connection reset")
        with self.assertRaises(llm.LLMUnavailable), self.assertLogs("core.llm", "WARNING"):
            llm.chat([{"role": "user", "content": "Hi"}])

    def test_empty_reply_becomes_llm_unavailable(self):
        self.create.return_value = fake_response(None)
        with self.assertRaises(llm.LLMUnavailable):
            llm.chat([{"role": "user", "content": "Hi"}])


class NotConfiguredTests(SimpleTestCase):
    @override_settings(OPENROUTER_API_KEY="", OPENROUTER_MODEL="test/model")
    def test_missing_key(self):
        self.assertFalse(llm.configured())
        with mock.patch("core.llm.OpenAI") as openai_cls, self.assertRaises(llm.LLMUnavailable):
            llm.chat([{"role": "user", "content": "Hi"}])
        openai_cls.assert_not_called()

    @override_settings(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="")
    def test_missing_model(self):
        self.assertFalse(llm.configured())


@override_settings(**CONFIGURED)
class CheckOpenRouterCommandTests(SimpleTestCase):
    def test_success(self):
        out = StringIO()
        with mock.patch("core.management.commands.check_openrouter.chat", return_value="Hello!"):
            call_command("check_openrouter", stdout=out)
        self.assertIn("OpenRouter OK (test/model): Hello!", out.getvalue())

    def test_failure(self):
        with mock.patch("core.management.commands.check_openrouter.chat", side_effect=llm.LLMUnavailable("down.")):
            with self.assertRaises(CommandError):
                call_command("check_openrouter")
