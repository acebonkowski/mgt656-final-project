from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.llm import LLMUnavailable, chat


class Command(BaseCommand):
    help = "Send one tiny OpenRouter request to verify the key and model on this environment (uses credits)."

    def handle(self, *args, **options):
        try:
            reply = chat([{"role": "user", "content": "Say hello."}], max_tokens=32)
        except LLMUnavailable as exc:
            raise CommandError(f"{exc} Check OPENROUTER_API_KEY and OPENROUTER_MODEL.") from exc
        self.stdout.write(self.style.SUCCESS(f"OpenRouter OK ({settings.OPENROUTER_MODEL}): {reply.strip()}"))
