from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Document


def validate_upload(upload) -> None:
    suffix = Path(upload.name).suffix.lower()
    if suffix not in settings.RAG_ALLOWED_EXTENSIONS:
        allowed = ", ".join(settings.RAG_ALLOWED_EXTENSIONS)
        raise ValidationError(f"Unsupported file type. Allowed: {allowed}.")
    if upload.size > settings.RAG_MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File is too large. Maximum size is {settings.RAG_MAX_UPLOAD_MB} MB."
        )


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ("title", "file")
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Optional title"}),
            "file": forms.ClearableFileInput(
                attrs={"accept": ".pdf,.txt,.md,.markdown,.docx", "class": "sr-only"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False
        self.fields["title"].widget.attrs.setdefault("class", "field-input")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        validate_upload(upload)
        return upload
