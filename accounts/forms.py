from django import forms

from accounts import usernames
from accounts.models import Profile


class UsernameFieldMixin:
    """The required username field shared by onboarding and /username/ (#95)."""

    def add_username_field(self):
        field = self.fields["username"]
        field.required = True
        field.label = "Username"
        field.help_text = usernames.RULES_HELP
        field.widget.attrs.update({
            "autocomplete": "username",
            "autocapitalize": "none",
            "spellcheck": "false",
            "maxlength": str(usernames.MAX_LENGTH),
        })

    def clean_username(self):
        username = usernames.normalize(self.cleaned_data.get("username"))
        if not username:
            raise forms.ValidationError("This field is required.", code="required")
        usernames.validate_username(username)
        if usernames.is_taken(username, exclude_profile_pk=self.instance.pk):
            raise forms.ValidationError(usernames.TAKEN_MESSAGE, code="taken")
        return username


class UsernameForm(UsernameFieldMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["username"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_username_field()
        self.fields["username"].widget.attrs["aria-describedby"] = "username-help username-errors"
