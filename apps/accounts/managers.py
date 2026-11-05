from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Email-first user manager (no username field)."""

    use_in_migrations = True

    def _normalize(self, email: str) -> str:
        if not email:
            raise ValueError("An email address is required.")
        return self.normalize_email(email).lower()

    def create_user(self, email, password=None, **extra_fields):
        email = self._normalize(email)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)
