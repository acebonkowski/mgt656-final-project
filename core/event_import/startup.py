"""Optional background import when a WSGI server process starts."""
import logging
from threading import Thread

from django.conf import settings
from django.db import close_old_connections

from .runner import acquire_lock, next_days_window, run_import

logger = logging.getLogger(__name__)


def background_startup_import():
    close_old_connections()
    try:
        starts_from, until = next_days_window(7)
        token = acquire_lock()
        if token is None:
            logger.info("event_import startup skipped=already_running")
            return
        # The shared runner releases the lock, including on failure.
        run_import(token, starts_from=starts_from, until=until)
    except Exception as exc:
        # Missing migrations/provider failures must not prevent the app serving.
        logger.error("event_import startup_failed type=%s", type(exc).__name__)
    finally:
        close_old_connections()


def start_import_on_startup():
    if not settings.AGGREGATOR_IMPORT_ON_STARTUP:
        return
    if not settings.MAP_API_KEY and not settings.TICKETMASTER_API_KEY:
        logger.warning("event_import startup skipped=no_provider_keys")
        return
    try:
        # Acquire the database lock inside the thread so startup never waits on
        # a database connection or a feed. Other workers share the same lock.
        Thread(target=background_startup_import, daemon=True, name="startup-event-import").start()
    except Exception as exc:
        logger.error("event_import startup_thread_failed type=%s", type(exc).__name__)
