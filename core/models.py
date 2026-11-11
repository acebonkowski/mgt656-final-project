from django.db import models


class School(models.Model):
    name = models.CharField(max_length=200, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Program(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="programs")
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_school_program")
        ]

    def __str__(self):
        return self.name


class ProfilePhoto(models.Model):
    """Upload history: removal detaches the photo; objects remain recoverable."""

    profile = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="photos")
    object_key = models.CharField(max_length=500, unique=True)
    content_type = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)
