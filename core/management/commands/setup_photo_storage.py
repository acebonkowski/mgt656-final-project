from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from core.photo_storage import ensure_bucket, StorageUnavailable


class Command(BaseCommand):
    help = "Create or verify the private profile photo bucket in the configured Supabase project."

    def handle(self, *args, **options):
        try:
            ensure_bucket(settings.SUPABASE_PHOTO_BUCKET)
            ensure_bucket(settings.SUPABASE_EVENT_PHOTO_BUCKET)
        except StorageUnavailable as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Private photo bucket and limits verified. Review bucket RLS policies before release."))
