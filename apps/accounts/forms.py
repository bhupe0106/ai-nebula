from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Profile, User


class SignupForm(UserCreationForm):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "placeholder": "you@example.com", "autofocus": True}
        )
    )
    display_name = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ada Lovelace"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "display_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Email"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower()
        user.display_name = self.cleaned_data.get("display_name", "").strip()
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "placeholder": "you@example.com", "autofocus": True}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")


class ProfileForm(forms.ModelForm):
    display_name = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Your display name"}),
    )

    class Meta:
        model = Profile
        fields = ("avatar", "bio")
        widgets = {
            "bio": forms.Textarea(
                attrs={"rows": 4, "placeholder": "A short note about you (optional)."}
            ),
            "avatar": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["display_name"].initial = user.display_name
        for name, field in self.fields.items():
            if name == "avatar":
                field.widget.attrs.setdefault("class", "file-input")
            else:
                field.widget.attrs.setdefault("class", "field-input")

    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.user is not None:
            self.user.display_name = self.cleaned_data.get("display_name", "").strip()
            if commit:
                self.user.save(update_fields=["display_name"])
        if commit:
            profile.save()
        return profile
