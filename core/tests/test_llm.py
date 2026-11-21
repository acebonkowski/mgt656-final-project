"""OpenRouter wrapper tests. The real API is never called: the OpenAI client
is replaced with a mock in every test."""

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings
from openai import BadRequestError, OpenAIError

from core import llm

CONFIGURED = dict(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="test/model",
                  OPENROUTER_IMAGE_MODEL="test/image-model")


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

    def test_generate_image_requires_data_url_and_never_uses_network(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            images=[{"image_url": {"url": "data:image/png;base64,aGVsbG8="}}]
        ))])
        self.create.return_value = response
        data, content_type = llm.generate_image("A campus event")
        self.assertEqual(data, b"hello")
        self.assertEqual(content_type, "image/png")
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["modalities"], ["image", "text"])

    def test_generate_image_uses_image_model_not_text_model(self):
        self.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            images=[{"image_url": {"url": "data:image/png;base64,aGVsbG8="}}]
        ))])
        llm.generate_image("A campus event")
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "test/image-model")
        self.assertEqual(kwargs["max_tokens"], llm.IMAGE_MAX_TOKENS)
        self.assertGreaterEqual(kwargs["max_tokens"], 2048)
        client_kwargs = self.openai_cls.call_args.kwargs
        self.assertEqual(client_kwargs["base_url"], "https://openrouter.ai/api/v1")
        # One attempt that ends before gunicorn's 30 s worker timeout.
        self.assertEqual(client_kwargs["max_retries"], 0)
        self.assertLess(client_kwargs["timeout"], 30)

    @override_settings(OPENROUTER_MODEL="")
    def test_generate_image_does_not_need_text_model(self):
        self.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            images=[{"image_url": {"url": "data:image/png;base64,aGVsbG8="}}]
        ))])
        data, _ = llm.generate_image("A campus event")
        self.assertEqual(data, b"hello")

    def test_generate_image_provider_error_logs_status_and_message_not_key_or_prompt(self):
        body = {"message": "test/image-model is not a valid model ID", "code": 400,
                "metadata": {"raw": "upstream detail"}}
        response = SimpleNamespace(status_code=400, request=None, headers={})
        self.create.side_effect = BadRequestError(
            f"Error code: 400 - {{'error': {body}}}", response=response, body=body,
        )
        prompt = "Secret party at the Elm Street loft"
        with self.assertLogs("core.llm", "WARNING") as logs, self.assertRaises(llm.LLMUnavailable) as caught:
            llm.generate_image(prompt)
        output = "\n".join(logs.output)
        self.assertIn("BadRequestError", output)
        self.assertIn("status=400", output)
        self.assertIn("test/image-model is not a valid model ID", output)
        self.assertIn("model=test/image-model", output)
        self.assertNotIn("fake-key", output)
        self.assertNotIn(prompt, output)
        self.assertNotIn("upstream detail", output)
        # Users get the generic message, not the provider's.
        self.assertEqual(str(caught.exception), "The AI image service is temporarily unavailable.")

    def test_generate_image_connection_error_logs_without_status(self):
        self.create.side_effect = OpenAIError("Connection error.")
        with self.assertLogs("core.llm", "WARNING") as logs, self.assertRaises(llm.LLMUnavailable):
            llm.generate_image("A campus event")
        self.assertIn("status=- message=Connection error.", logs.output[0])

    def test_generate_image_empty_response_becomes_llm_unavailable(self):
        self.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(images=[])
        )])
        with self.assertRaises(llm.LLMUnavailable):
            llm.generate_image("A campus event")


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

    @override_settings(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="test/model", OPENROUTER_IMAGE_MODEL="")
    def test_missing_image_model_sends_no_request(self):
        self.assertFalse(llm.image_configured())
        with mock.patch("core.llm.OpenAI") as openai_cls, self.assertRaises(llm.LLMNotConfigured) as caught:
            llm.generate_image("A campus event")
        self.assertEqual(str(caught.exception), "AI image generation is not configured.")
        openai_cls.assert_not_called()

    @override_settings(OPENROUTER_API_KEY="", OPENROUTER_IMAGE_MODEL="test/image-model")
    def test_missing_key_blocks_image_generation(self):
        with mock.patch("core.llm.OpenAI") as openai_cls, self.assertRaises(llm.LLMNotConfigured):
            llm.generate_image("A campus event")
        openai_cls.assert_not_called()

    def test_not_configured_is_still_llm_unavailable(self):
        # Existing callers that catch LLMUnavailable keep working.
        self.assertTrue(issubclass(llm.LLMNotConfigured, llm.LLMUnavailable))


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


@override_settings(**CONFIGURED)
class ChatJsonTests(SimpleTestCase):
    """Structured output for AI search (#36)."""

    SCHEMA = {"type": "object", "properties": {"reply": {"type": "string"}}}

    def setUp(self):
        patcher = mock.patch("core.llm.OpenAI")
        self.create = patcher.start().return_value.chat.completions.create
        self.addCleanup(patcher.stop)

    def test_sends_a_strict_json_schema_and_parses_the_reply(self):
        self.create.return_value = fake_response('{"reply": "Hi"}')
        self.assertEqual(llm.chat_json([], "test", self.SCHEMA), {"reply": "Hi"})
        response_format = self.create.call_args.kwargs["response_format"]
        self.assertEqual(response_format["json_schema"],
                         {"name": "test", "strict": True, "schema": self.SCHEMA})
        self.assertEqual(self.create.call_args.kwargs["timeout"], 20)

    def test_accepts_json_in_a_code_fence(self):
        self.create.return_value = fake_response('```json\n{"reply": "Hi"}\n```')
        self.assertEqual(llm.chat_json([], "test", self.SCHEMA), {"reply": "Hi"})

    def test_model_can_be_overridden(self):
        self.create.return_value = fake_response("{}")
        llm.chat_json([], "test", self.SCHEMA, model="other/model")
        self.assertEqual(self.create.call_args.kwargs["model"], "other/model")

    def test_non_json_is_invalid_and_logged(self):
        self.create.return_value = fake_response("Sure! Here are some events")
        with self.assertRaises(llm.LLMInvalidResponse), self.assertLogs("core.llm", "WARNING"):
            llm.chat_json([], "test", self.SCHEMA)

    def test_empty_or_non_object_is_invalid(self):
        for content in ("[1, 2]", ""):
            self.create.return_value = fake_response(content)
            with self.subTest(content=content), self.assertRaises(llm.LLMInvalidResponse):
                llm.chat_json([], "test", self.SCHEMA)

    def test_invalid_response_is_still_an_llm_unavailable(self):
        self.assertTrue(issubclass(llm.LLMInvalidResponse, llm.LLMUnavailable))

