"""Extraction, chunking, embedding, and retrieval."""
from __future__ import annotations

from apps.llm.mock import MockLLM
from apps.llm.mock import MockLLM

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db.models import Q

from apps.llm import get_llm
from apps.llm.tokens import estimate_tokens
from apps.usage.models import UsageEvent
from apps.usage.services import arecord_usage

from .models import Document, DocumentChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- extraction
def extract_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return _extract_plain(path)
    raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")


def _extract_plain(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # pragma: no cover - malformed page
            logger.warning("Could not extract a page from %s", path.name)
    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


# ------------------------------------------------------------------ chunking
def split_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split text into overlapping windows, preferring paragraph/word breaks."""
    chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
    overlap = settings.RAG_CHUNK_OVERLAP if overlap is None else overlap
    chunk_size = max(200, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size // 2))

    normalized = re.sub(r"\r\n?", "\n", text or "")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    length = len(normalized)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            window = normalized[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind(" "))
            if cut > int(chunk_size * 0.55):
                end = start + cut + 1
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


# ---------------------------------------------------------------- embeddings
async def aembed_in_batches(
    texts: list[str],
    *,
    user=None,
    conversation=None,
) -> list[list[float]]:
    if not texts:
        return []

    client = MockLLM()
    batch_size = max(1, settings.RAG_EMBED_BATCH_SIZE)
    vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(await client.embed(batch))

        if user is not None:
            await arecord_usage(
                user=user,
                kind=UsageEvent.Kind.EMBEDDING,
                conversation=conversation,
                model="mock-embeddings-256",
                prompt_tokens=sum(estimate_tokens(text) for text in batch),
            )

    return vectors

# ----------------------------------------------------------------- ingestion
def ingest_document_sync(document_id) -> Document:
    document = Document.objects.select_related("user", "conversation").get(pk=document_id)
    if document.status == Document.Status.READY and document.chunk_count:
        return document
    Document.objects.filter(pk=document.pk).update(
        status=Document.Status.PROCESSING, error=""
    )
    try:
        text = extract_text(document.file.path)
        chunks = split_text(text)
        if not chunks:
            raise ValueError("No readable text was found in this file.")

        vectors = embed_in_batches(chunks, user=document.user, conversation=document.conversation)
        if len(vectors) != len(chunks):
            raise ValueError("The embedding provider returned an unexpected vector count.")

        DocumentChunk.objects.filter(document=document).delete()
        DocumentChunk.objects.bulk_create(
            [
                DocumentChunk(
                    document=document,
                    index=index,
                    content=chunk,
                    embedding=vector,
                    token_count=estimate_tokens(chunk),
                )
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            ],
            batch_size=100,
        )
        Document.objects.filter(pk=document.pk).update(
            status=Document.Status.READY,
            error="",
            chunk_count=len(chunks),
        )
    except Exception as exc:  # noqa: BLE001 - report any ingestion failure to the user
        logger.exception("Document ingestion failed for %s", document.pk)
        Document.objects.filter(pk=document.pk).update(
            status=Document.Status.FAILED, error=str(exc)[:1000]
        )
    document.refresh_from_db()
    return document


def queue_ingestion(document: Document) -> Document:
    """Hand a document to Celery, falling back to inline ingestion.

    Inline fallback keeps uploads working when Redis/Celery is not running.
    """
    from .tasks import ingest_document_task

    try:
        ingest_document_task.delay(str(document.id))
    except Exception:  # pragma: no cover - broker unavailable
        logger.warning("Celery unavailable; ingesting document inline", exc_info=True)
        ingest_document_sync(document.id)
    document.refresh_from_db()
    return document


# ----------------------------------------------------------------- retrieval
@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: object
    title: str
    content: str
    score: float
    index: int


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for index in range(size):
        a = float(left[index])
        b = float(right[index])
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


async def aretrieve(
    query: str,
    *,
    user,
    conversation=None,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    if user is None or not (query or "").strip():
        return []

    chunks_qs = DocumentChunk.objects.filter(
        document__user=user, document__status=Document.Status.READY
    ).select_related("document")
    if conversation is not None:
        chunks_qs = chunks_qs.filter(
            Q(document__conversation=conversation) | Q(document__conversation__isnull=True)
        )
    chunks_qs = chunks_qs.order_by("document_id", "index")[: settings.RAG_MAX_CANDIDATES]
    chunks = [chunk async for chunk in chunks_qs]
    if not chunks:
        return []

    vectors = await MockLLM().embed([query])
    if not vectors:
        return []
    query_vector = vectors[0]
    await arecord_usage(
        user=user,
        kind=UsageEvent.Kind.EMBEDDING,
        conversation=conversation,
        model=settings.LLM_EMBEDDING_MODEL,
        prompt_tokens=estimate_tokens(query),
    )

    scored: list[RetrievedChunk] = []
    for chunk in chunks:
        if not chunk.embedding:
            continue
        score = cosine_similarity(query_vector, chunk.embedding)
        if score < settings.RAG_MIN_SCORE:
            continue
        scored.append(
            RetrievedChunk(
                chunk_id=chunk.pk,
                document_id=chunk.document_id,
                title=chunk.document.display_title,
                content=chunk.content,
                score=score,
                index=chunk.index,
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[: (limit or settings.RAG_TOP_K)]


def retrieve(*args, **kwargs) -> list[RetrievedChunk]:
    return async_to_sync(aretrieve)(*args, **kwargs)


def format_context(results: list[RetrievedChunk]) -> str:
    blocks = []
    for position, result in enumerate(results, start=1):
        blocks.append(
            f"[{position}] {result.title} (relevance {result.score:.2f})\n{result.content}"
        )
    return "\n\n".join(blocks)
