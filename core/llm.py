"""Server-side OpenRouter client (OpenAI-compatible API).

Only the server holds OPENROUTER_API_KEY. Never call this from a template or
pass the key or raw provider responses to the browser. Tests must mock
`get_client` (or `chat`) and never reach the real API.
"""

import logging

from django.conf import settings
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 30


class LLMUnavailable(Exception):
    pass


def configured():
    return bool(settings.OPENROUTER_API_KEY and settings.OPENROUTER_MODEL)


def get_client():
    if not configured():
        raise LLMUnavailable("The AI service is not configured.")
    return OpenAI(
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        timeout=TIMEOUT_SECONDS,
        max_retries=1,
    )


def chat(messages, max_tokens=256, **kwargs):
    """Send a chat completion and return the reply text.

    `messages` uses the OpenAI format: [{"role": "user", "content": "..."}].
    Extra kwargs (e.g. temperature, response_format) go straight to the API.
    """
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs,
        )
    except OpenAIError as exc:
        # Provider errors can echo request details; log the type only.
        logger.warning("OpenRouter request failed (%s)", type(exc).__name__)
        raise LLMUnavailable("The AI service is temporarily unavailable.") from exc
    if not response.choices or response.choices[0].message.content is None:
        raise LLMUnavailable("The AI service returned an empty response.")
    return response.choices[0].message.content
