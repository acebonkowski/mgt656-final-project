from django.apps import AppConfig


class AbtestConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "abtest"
    verbose_name = "A/B test"
