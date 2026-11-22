from django.conf import settings
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


class Event(models.Model):
    class Category(models.TextChoices):
        MUSIC_PERFORMANCE = "music_performance", "Music & Performance"
        ART_FILM_EXHIBITS = "art_film_exhibits", "Art, Film & Exhibits"
        FESTIVALS_SEASONAL = "festivals_seasonal", "Festivals & Seasonal"
        TALKS_PANELS = "talks_panels", "Talks & Panels"
        WORKSHOPS_SKILLS = "workshops_skills", "Workshops & Skills"
        CAREER_NETWORKING = "career_networking", "Career & Networking"
        SOCIAL_COMMUNITY = "social_community", "Social & Community"
        FOOD_DRINK = "food_drink", "Food & Drink"
        SPORTS_OUTDOORS_WELLNESS = "sports_outdoors_wellness", "Sports, Outdoors & Wellness"
        SERVICE_CIVIC = "service_civic", "Service, Civic & Advocacy"
        FAITH_SPIRITUALITY = "faith_spirituality", "Faith & Spirituality"
        CAMPUS_ADMIN = "campus_admin", "Campus & Admin"

    image = models.CharField(max_length=500)
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=150)
    category = models.CharField(max_length=32, choices=Category.choices)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    location = models.CharField(max_length=500)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    link = models.URLField(max_length=2048, blank=True)  # optional since #69
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    source = models.CharField(max_length=100, blank=True)
    external_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["start_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~models.Q(source="") & ~models.Q(external_id=""),
                name="event_source_external_id_unique",
            ),
            models.UniqueConstraint(
                fields=["location", "start_at", "end_at"],
                name="event_location_interval_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="event_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="event_end_after_start",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def price_label(self):
        # Imported events (#33) may have no price.
        if self.price is None:
            return "Price not listed"
        return "Free" if self.price == 0 else f"${self.price:.2f}"

    @property
    def source_label(self):
        return {"yale_connect": "Yale Connect", "som": "Yale SOM",
                "ticketmaster": "Ticketmaster"}.get(self.source, self.source)

    @property
    def address(self):
        return self.location

    @address.setter
    def address(self, value):
        self.location = value

    @property
    def start(self):
        return self.start_at

    @start.setter
    def start(self, value):
        self.start_at = value

    @property
    def end(self):
        return self.end_at

    @end.setter
    def end(self, value):
        self.end_at = value


class AIUsage(models.Model):
    """
    One row per OpenRouter call made for a user (#36), including failed calls,
    since they still use credits. Counted by core.ai_limits.
    """

    class Kind(models.TextChoices):
        SEARCH = "search", "AI search message"
        IMAGE_SEARCH = "image_search", "AI search with an image"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # keep the row so the global daily cap still counts it
        null=True,
        related_name="ai_usage",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"], name="core_aiusage_user_time_idx"),
        ]

    def __str__(self):
        return f"{self.kind} by {self.user_id} at {self.created_at:%Y-%m-%d %H:%M}"


class EventImportLock(models.Model):
    name = models.CharField(max_length=40, primary_key=True)
    token = models.CharField(max_length=36, blank=True)
    started_at = models.DateTimeField(null=True)


class EventGeocodeCache(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    result = models.JSONField(null=True)
    updated_at = models.DateTimeField(auto_now=True)
