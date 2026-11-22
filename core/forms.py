from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal
import base64
import binascii
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from accounts.models import Profile
from core.models import Event, Program, School
from core.photo_validation import validate_event_photo
from core.photo_storage import StorageUnavailable


class OnboardingForm(forms.ModelForm):
    display_name = forms.CharField(max_length=100, label="First name or nickname",
                                  widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    school = forms.ModelChoiceField(queryset=School.objects.filter(is_active=True), empty_label="Choose your school")

    class Meta:
        model = Profile
        fields = ["display_name", "school", "program"]
        labels = {"display_name": "First name or nickname", "program": "Program at Yale"}
        widgets = {"display_name": forms.TextInput(attrs={"autocomplete": "given-name"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school"].label = "School at Yale"
        self.fields["program"].empty_label = "Choose your program"
        self.fields["program"].queryset = Program.objects.none()
        school_id = self.data.get("school") if self.is_bound else None
        self.fields["program"].required = True
        if not self.is_bound and self.instance.program_id:
            school_id = self.instance.program.school_id
            self.initial["school"] = school_id
        try:
            school_id = int(school_id)
        except (ValueError, TypeError):
            school_id = None
        if school_id is not None:
            self.fields["program"].queryset = Program.objects.filter(school_id=school_id, school__is_active=True)
        for name, field in self.fields.items():
            field.widget.attrs["aria-describedby"] = f"{name}-errors"
            if self.is_bound and name in self.errors:
                field.widget.attrs["aria-invalid"] = "true"


class CoordinateField(forms.DecimalField):
    """DecimalField that rounds extra precision instead of rejecting it.

    Geocoders return coordinates with ~14 decimal places; the hidden inputs
    must still validate against the model's 6 (#55). Rounding happens in
    to_python so it runs before the max_digits/decimal_places validators.
    """

    def to_python(self, value):
        value = super().to_python(value)
        if value is None or not value.is_finite():
            return value
        return value.quantize(Decimal(1).scaleb(-self.decimal_places), rounding=ROUND_HALF_UP)


def to_24_hour(hour, minute, period):
    """("8", "00", "PM") -> "20:00"; None if it isn't a valid 12-hour time.

    Mirrors Time12.to24 in core/static/core/time12.js (#67). An empty minute
    means :00.
    """
    hour, minute = str(hour or "").strip(), str(minute or "").strip()
    if not re.fullmatch(r"\d{1,2}", hour) or (minute and not re.fullmatch(r"\d{1,2}", minute)):
        return None
    if period not in ("AM", "PM"):
        return None
    h, m = int(hour), int(minute or 0)
    if not 1 <= h <= 12 or m > 59:
        return None
    return f"{h % 12 + (12 if period == 'PM' else 0):02d}:{m:02d}"


TWELVE_HOUR_RE = re.compile(r"^\s*(\d{0,2}):(\d{0,2}) (AM|PM)?\s*$")


def to_12_hour(value):
    """A time, "HH:MM" or an unparsed "h:mm PM" -> (hour, minute, period) for display."""
    if isinstance(value, time):
        return str(value.hour % 12 or 12), f"{value.minute:02d}", "AM" if value.hour < 12 else "PM"
    text = str(value or "")
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", text)
    if match and int(match.group(1)) < 24:
        h, m = int(match.group(1)), match.group(2)
        return str(h % 12 or 12), m, "AM" if h < 12 else "PM"
    match = TWELVE_HOUR_RE.match(text)
    if match:  # what the user typed, sent back with the error
        return match.group(1), match.group(2), match.group(3) or "PM"
    return "", "", "PM"


class TwelveHourTimeWidget(forms.Widget):
    """Hour, minute and an AM/PM switch, posted as <name>_hour/_minute/_period (#69).

    Uses the same markup as the search panel's start times (#67). The field
    still receives a 24-hour "HH:MM" string, so TimeField validates it. A
    plain "HH:MM" under the field's own name is accepted too.
    """

    template_name = "core/widgets/time12.html"

    def value_from_datadict(self, data, files, name):
        if name in data:
            return data[name]
        hour = data.get(f"{name}_hour", "").strip()
        minute = data.get(f"{name}_minute", "").strip()
        period = data.get(f"{name}_period", "")
        if not hour and not minute:
            return ""
        # Invalid input goes through unchanged so TimeField rejects it and the
        # user sees what they typed.
        return to_24_hour(hour, minute, period) or f"{hour}:{minute} {period}"

    def value_omitted_from_data(self, data, files, name):
        return name not in data and f"{name}_hour" not in data

    def id_for_label(self, id_):
        return f"{id_}_hour" if id_ else id_

    def get_context(self, name, value, attrs):
        attrs = self.build_attrs(self.attrs, attrs)
        hour, minute, period = to_12_hour(value)
        return {
            "id": attrs.get("id", f"id_{name}"), "name": name, "label": attrs.get("aria-label", ""),
            "hour": hour, "minute": minute, "period": period, "required": self.is_required,
        }

    def render(self, name, value, attrs=None, renderer=None):
        return mark_safe(render_to_string(self.template_name, self.get_context(name, value, attrs)))


class EventForm(forms.Form):
    image = forms.FileField(
        label="Image",
        help_text="PNG, JPEG or HEIC, no larger than 5 MB.",
        required=False,
    )
    ai_image = forms.CharField(required=False, widget=forms.HiddenInput)
    # Compact form (#69): "Title" with live counters, 12-hour times.
    name = forms.CharField(max_length=30, label="Title",
                           widget=forms.TextInput(attrs={"aria-describedby": "id_name_count"}))
    description = forms.CharField(max_length=150, widget=forms.Textarea(
        attrs={"rows": 2, "aria-describedby": "id_description_count"}))
    category = forms.ChoiceField(choices=Event.Category.choices)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=TwelveHourTimeWidget(attrs={"aria-label": "Start time"}))
    end_time = forms.TimeField(widget=TwelveHourTimeWidget(attrs={"aria-label": "End time"}))
    location = forms.CharField(max_length=500, label="Address")
    location_confirmed = forms.CharField(required=False, widget=forms.HiddenInput)
    latitude = CoordinateField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
        widget=forms.HiddenInput,
    )
    longitude = CoordinateField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
        widget=forms.HiddenInput,
    )
    remove_image = forms.BooleanField(required=False, widget=forms.HiddenInput)
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"),
                               widget=forms.NumberInput(attrs={"placeholder": "0 for free"}))
    link = forms.URLField(max_length=2048, required=False,
                          widget=forms.URLInput(attrs={"placeholder": "Optional"}))

    def __init__(self, *args, existing_image=None, **kwargs):
        kwargs.setdefault("label_suffix", "")  # "Title", not "Title:" (#69)
        super().__init__(*args, **kwargs)
        self.existing_image = existing_image

    def clean_image(self):
        upload = self.cleaned_data.get("image")
        ai_image = self.data.get("ai_image", "")
        remove_image = self.data.get("remove_image") in ("1", "true", "True", "on")
        if remove_image:
            raise forms.ValidationError("Choose an image.")
        if self.existing_image and not upload and not ai_image:
            self.event_image = None
            return self.existing_image
        if not upload and not ai_image:
            raise forms.ValidationError("Choose an image.")
        if ai_image and not upload:
            header, separator, encoded = ai_image.partition(",")
            if not separator or not header.startswith("data:image/"):
                raise forms.ValidationError("The generated image is invalid.")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise forms.ValidationError("The generated image is invalid.") from exc
            content_type = header.partition(";")[0].replace("data:", "")
            upload = SimpleUploadedFile("ai-event-image." + ("jpg" if content_type == "image/jpeg" else "png"),
                                        raw, content_type=content_type)
        try:
            data, content_type = validate_event_photo(upload)
        except ValidationError:
            raise
        except StorageUnavailable:
            raise forms.ValidationError("Photo uploads are temporarily unavailable.")
        self.event_image = (data, content_type)
        return upload

    def clean_link(self):
        link = self.cleaned_data["link"]
        if not link:
            return ""  # optional (#69)
        parsed = urlsplit(link)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError("Enter a valid http(s) URL.")
        return link

    def clean(self):
        cleaned = super().clean()
        location = cleaned.get("location")
        location_confirmed = cleaned.get("location_confirmed")
        if location and not location_confirmed:
            self.add_error("location", "Select an address from the suggestions.")
        elif location and location_confirmed != location:
            self.add_error("location", "Select an address from the suggestions.")
        date = cleaned.get("date")
        start_time = cleaned.get("start_time")
        end_time = cleaned.get("end_time")
        if date and start_time and end_time:
            new_york = ZoneInfo("America/New_York")
            start_at = datetime.combine(date, start_time, tzinfo=new_york)
            end_at = datetime.combine(date, end_time, tzinfo=new_york)
            if end_at <= start_at:
                raise ValidationError("End time must be after start time.")
            cleaned["start_at"] = start_at
            cleaned["end_at"] = end_at
        return cleaned

    def save(self, creator, image_key=None, instance=None):
        cleaned = self.cleaned_data
        values = {
            "image": image_key or self.existing_image or cleaned["image"].name,
            "name": cleaned["name"],
            "description": cleaned["description"],
            "category": cleaned["category"],
            "start_at": cleaned["start_at"],
            "end_at": cleaned["end_at"],
            "location": cleaned["location"],
            "latitude": cleaned["latitude"],
            "longitude": cleaned["longitude"],
            "price": cleaned["price"],
            "link": cleaned["link"],
            "creator": creator,
        }
        if instance is not None:
            for field, value in values.items():
                setattr(instance, field, value)
            instance.save()
            return instance
        return Event.objects.create(**values)
