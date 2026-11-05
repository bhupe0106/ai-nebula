import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


def avatar_upload_to(instance, filename: str) -> str:
    suffix = Path(filename).suffix.lower() or ".png"
    return f"avatars/{instance.user_id}/{uuid.uuid4().hex}{suffix}"


class User(AbstractUser):
    """Custom user identified by email instead of username."""

    username = None
    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=120, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.display_name or self.email

    @property
    def name(self) -> str:
        return self.display_name or self.email.split("@")[0]

    @property
    def initials(self) -> str:
        source = self.display_name or self.email
        parts = source.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return source[:2].upper()


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    avatar = models.ImageField(upload_to=avatar_upload_to, blank=True, null=True)
    bio = models.TextField(blank=True, max_length=500)
    monthly_token_quota = models.PositiveBigIntegerField(
        default=settings.DEFAULT_MONTHLY_TOKEN_QUOTA,
        help_text="Maximum tokens this account may use per calendar month.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile of {self.user}"
