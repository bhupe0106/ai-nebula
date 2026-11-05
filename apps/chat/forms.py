from django import forms
from django.conf import settings

from .models import Conversation


class MessageForm(forms.Form):
    content = forms.CharField(
        max_length=8000,
        widget=forms.Textarea(
            attrs={
                "rows": 1,
                "placeholder": "Ask anything…",
                "class": "composer-input",
                "autocomplete": "off",
                "data-composer": "true",
            }
        ),
    )

    def clean_content(self):
        content = (self.cleaned_data["content"] or "").strip()
        if not content:
            raise forms.ValidationError("Write a message first.")
        return content


class ConversationSettingsForm(forms.ModelForm):
    class Meta:
        model = Conversation
        fields = ("title", "model", "temperature", "system_prompt", "use_documents")
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Conversation title"}),
            "temperature": forms.NumberInput(attrs={"min": 0, "max": 2, "step": 0.1}),
            "system_prompt": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "You are a concise, helpful assistant…",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", f"Default — {settings.LLM_CHAT_MODEL}")]
        choices += [(name, name) for name in settings.LLM_MODEL_CHOICES if name]
        current = getattr(self.instance, "model", "")
        if current and all(value != current for value, _label in choices):
            choices.append((current, current))
        self.fields["model"].choices = choices
        self.fields["model"].required = False
        self.fields["title"].required = True

        for name, field in self.fields.items():
            if name == "use_documents":
                field.widget.attrs.setdefault("class", "checkbox-input")
            else:
                field.widget.attrs.setdefault("class", "field-input")
