from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from accounts import usernames


class Profile(models.Model):
    """Shared by OTP login (#6) and onboarding (#7)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    # False: the user is sent to onboarding (#7) after login. True: to the map (#8).
    onboarding_complete = models.BooleanField(default=False)
    display_name = models.CharField(max_length=100, blank=True)
    # A user exists before onboarding. The form requires a program on completion.
    program = models.ForeignKey("core.Program", on_delete=models.PROTECT, null=True, blank=True)
    photo_reference = models.CharField(max_length=500, blank=True)

    class AttendanceVisibility(models.TextChoices):
        FRIENDS = "friends", "Friends"
        PROGRAM = "program", "My program"
        SCHOOL = "school", "My school"
        EVERYONE = "everyone", "Everyone"

    # Who sees the events this user is going to (#83). Stored here; enforced
    # server-side by whatever shows other people's attendance (#41, #84, #85).
    attendance_visibility = models.CharField(
        max_length=10, choices=AttendanceVisibility.choices,
        default=AttendanceVisibility.EVERYONE,
    )
    # The handle friends search for (#95), stored lowercase. Blank until chosen:
    # users from before #95 are asked for one after login.
    username = models.CharField(
        max_length=usernames.MAX_LENGTH, blank=True, validators=[usernames.validate_username]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Unique in any letter case, enforced by the database (#95).
            models.UniqueConstraint(
                Lower("username"),
                condition=~models.Q(username=""),
                name="profile_username_ci_unique",
                violation_error_message=usernames.TAKEN_MESSAGE,
            ),
        ]

    def __str__(self):
        return f"profile of {self.user}"

    @property
    def school(self):
        return self.program.school if self.program_id else None


class LoginCode(models.Model):
    """The current one-time code for an email address (one row per address).

    Only a keyed hash of the code is stored. For the seeded grader addresses no
    code is stored; the row only tracks wrong tries and the lockout."""

    email = models.EmailField(unique=True)
    code_hash = models.CharField(max_length=128, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"login code for {self.email}"
