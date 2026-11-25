"""Use the existing manual search rules without map or attendance controls."""
from django import forms

from core.search import EventSearchForm


class FavoriteSearchForm(EventSearchForm):
    near_label = forms.CharField(required=False, max_length=300, label="Address (Optional)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("area", "include_not_going"):
            self.fields.pop(name)
        self.fields["q"].label = "Search Favorites"
        self.fields["q"].widget = forms.TextInput(attrs={"type": "search"})
        self.fields["category"].widget = forms.CheckboxSelectMultiple(
            choices=self.fields["category"].choices
        )
        for name in ("date_from", "date_to"):
            self.fields[name].widget = forms.DateInput(attrs={"type": "date"})
        for name in ("time_from", "time_to"):
            self.fields[name].widget = forms.TimeInput(attrs={"type": "time"})
        for name in ("near_lat", "near_lng"):
            self.fields[name].widget = forms.HiddenInput()
        self.fields["when"].label = "Date Preset"
        self.fields["radius_mi"].label = "Within"
