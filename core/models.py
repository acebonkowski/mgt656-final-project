from django.conf import settings
from django.db import models


class School(models.Model):
    name = models.CharField(max_length=200, unique=True)

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


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=100)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    # Store an object-storage key, never a local upload path or expiring signed URL.
    photo_reference = models.CharField(max_length=500, blank=True)

    @property
    def school(self):
        # Derive school from the program so inconsistent pairs cannot be persisted.
        return self.program.school
