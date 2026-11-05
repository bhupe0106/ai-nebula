import contextlib

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Document


@receiver(post_delete, sender=Document)
def delete_document_file(sender, instance, **kwargs):
    if not instance.file:
        return
    # The storage backend may have already removed the object.
    with contextlib.suppress(Exception):  # pragma: no cover - storage already gone
        instance.file.delete(save=False)
