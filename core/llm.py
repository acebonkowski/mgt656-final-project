"""Server-side OpenRouter client (OpenAI-compatible API).

Only the server holds OPENROUTER_API_KEY. Never call this from a template or
pass the key or raw provider responses to the browser. Tests must mock
`get_client` (or `chat`) and never reach the real API.
"""

import logging
import base64
import binascii
from urllib.parse import urlparse

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


def generate_image(prompt):
    """Generate one image through OpenRouter and return PNG/JPEG bytes.

    OpenRouter is the only provider and key-bearing request path. Provider
    image payloads are decoded only in this server-side module.
    """
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            extra_body={"modalities": ["image", "text"]},
        )
    except OpenAIError as exc:
        logger.warning("OpenRouter image request failed (%s)", type(exc).__name__)
        raise LLMUnavailable("The AI image service is temporarily unavailable.") from exc

    if not response.choices:
        raise LLMUnavailable("The AI image service returned no image.")
    message = response.choices[0].message
    images = getattr(message, "images", None) or []
    url = None
    for image in images:
        if isinstance(image, dict):
            image_url = image.get("image_url") or image
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
        else:
            url = getattr(image, "url", None)
            if url is None:
                image_url = getattr(image, "image_url", None)
                url = getattr(image_url, "url", None) if image_url is not None else None
        if url:
            break
    if not url:
        raise LLMUnavailable("The AI image service returned no image.")

    parsed = urlparse(url)
    if parsed.scheme == "data":
        header, separator, encoded = url.partition(",")
        if not separator:
            raise LLMUnavailable("The AI image service returned an invalid image.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise LLMUnavailable("The AI image service returned an invalid image.") from exc
        content_type = header.partition(";")[0].replace("data:", "") or "image/png"
        return data, content_type
    raise LLMUnavailable("The AI image service returned an unsupported image URL.")
