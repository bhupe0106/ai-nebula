from celery import shared_task

from .services import ingest_document_sync


@shared_task(ignore_result=True)
def ingest_document_task(document_id: str) -> str:
    """Extract, chunk, embed and store a document.

    With CELERY_TASK_ALWAYS_EAGER=True (default in development) this runs inline,
    so a single `runserver` is enough. In production it runs in a Celery worker.
    """
    document = ingest_document_sync(document_id)
    return document.status
