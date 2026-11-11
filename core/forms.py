from django import forms

from accounts.models import Profile
from core.models import Program, School


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
