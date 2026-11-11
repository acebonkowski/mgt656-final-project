import uuid

from django.db import models


class Variant(models.TextChoices):
    KUDOS = "kudos", "kudos"
    THANKS = "thanks", "thanks"


class Impression(models.Model):
    """One row per visitor: the first time they saw the A/B page."""

    visitor_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    variant = models.CharField(max_length=6, choices=Variant.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.variant} impression {self.visitor_id}"


class Click(models.Model):
    """At most one per visitor, enforced by the one-to-one link."""

    impression = models.OneToOneField(Impression, on_delete=models.CASCADE, related_name="click")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"click on {self.impression}"
