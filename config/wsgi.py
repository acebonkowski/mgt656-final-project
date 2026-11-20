"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# This entry point is loaded by runserver and the deployed Gunicorn workers,
# after Django initialization. Management commands don't trigger imports.
from core.event_import.startup import start_import_on_startup  # noqa: E402

start_import_on_startup()
