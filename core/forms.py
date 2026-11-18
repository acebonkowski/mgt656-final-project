from datetime import datetime
from decimal import Decimal
import base64
import binascii
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

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


class EventForm(forms.Form):
    image = forms.FileField(
        label="Image",
        help_text="PNG, JPEG or HEIC, no larger than 5 MB.",
        required=False,
    )
    ai_image = forms.CharField(required=False, widget=forms.HiddenInput)
    name = forms.CharField(max_length=30)
    description = forms.CharField(max_length=150, widget=forms.Textarea)
    category = forms.ChoiceField(choices=Event.Category.choices)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    location = forms.CharField(max_length=500, label="Address")
    location_confirmed = forms.CharField(required=False, widget=forms.HiddenInput)
    latitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
        widget=forms.HiddenInput,
    )
    longitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
        widget=forms.HiddenInput,
    )
    remove_image = forms.BooleanField(required=False, widget=forms.HiddenInput)
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    link = forms.URLField(max_length=2048)

    def __init__(self, *args, existing_image=None, **kwargs):
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
