import shutil
import tempfile
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Document, DocumentChunk
from .services import (
    aretrieve,
    cosine_similarity,
    format_context,
    ingest_document_sync,
    split_text,
)

User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="chatbot-test-media-")


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


class ChunkingTests(TestCase):
    def test_empty_text(self):
        self.assertEqual(split_text("   "), [])

    def test_short_text_is_one_chunk(self):
        self.assertEqual(split_text("hello world", chunk_size=1200), ["hello world"])

    def test_long_text_is_split_with_overlap(self):
        text = " ".join(f"word{i}" for i in range(1200))
        chunks = split_text(text, chunk_size=500, overlap=100)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 600 for chunk in chunks))

    def test_normalizes_line_endings(self):
        chunks = split_text("a\r\n\r\n\r\nb", chunk_size=500)
        self.assertEqual(chunks, ["a\n\nb"])


class SimilarityTests(TestCase):
    def test_cosine(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
        self.assertEqual(cosine_similarity([], [1, 2]), 0.0)
        self.assertEqual(cosine_similarity([0, 0], [1, 1]), 0.0)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, LLM_PROVIDER="mock", MOCK_LLM_DELAY=0)
class IngestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="rag@example.com", password="password12345")

    def _document(self, name="notes.txt", content=b"Vector databases store embeddings."):
        upload = SimpleUploadedFile(name, content, content_type="text/plain")
        return Document.objects.create(user=self.user, title=name, file=upload, size_bytes=upload.size)

    def test_ingest_creates_chunks(self):
        document = self._document()
        ingest_document_sync(document.pk)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.READY)
        self.assertGreater(document.chunk_count, 0)
        self.assertEqual(DocumentChunk.objects.filter(document=document).count(), document.chunk_count)
        first = document.chunks.first()
        self.assertTrue(first.embedding)

    def test_ingest_failure_is_recorded(self):
        document = self._document(name="bad.bin", content=b"\x00\x01binary")
        ingest_document_sync(document.pk)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("Unsupported", document.error)

    def test_retrieval_orders_by_similarity_and_filters_scope(self):
        document = self._document(content=b"neural networks and deep learning")
        ingest_document_sync(document.pk)
        results = async_to_sync(aretrieve)("neural networks", user=self.user)
        self.assertTrue(results)
        self.assertIn("neural", results[0].content.lower())
        self.assertGreater(results[0].score, 0)
        context = format_context(results)
        self.assertIn("[1]", context)

    def test_retrieval_without_documents(self):
        self.assertEqual(async_to_sync(aretrieve)("anything", user=self.user), [])

    def test_embedding_is_recorded_as_usage(self):
        document = self._document(content=b"usage tracking works")
        ingest_document_sync(document.pk)
        self.assertTrue(self.user.usage_events.filter(kind="embedding").exists())


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, LLM_PROVIDER="mock", MOCK_LLM_DELAY=0)
class DocumentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="docs@example.com", password="password12345")
        self.client.login(email="docs@example.com", password="password12345")

    def test_library_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("rag:library"))
        self.assertEqual(response.status_code, 302)

    def test_library_renders(self):
        response = self.client.get(reverse("rag:library"))
        self.assertEqual(response.status_code, 200)

    def test_upload_ingests_document(self):
        upload = SimpleUploadedFile(
            "notes.txt", b"Documents make answers better.", content_type="text/plain"
        )
        with patch(
            "apps.rag.views.queue_ingestion",
            side_effect=lambda document: ingest_document_sync(document.id),
        ):
            response = self.client.post(
                reverse("rag:upload"), {"file": upload, "title": "Notes"}
            )
        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(user=self.user)
        self.assertEqual(document.status, Document.Status.READY)

    def test_rejects_bad_extension(self):
        upload = SimpleUploadedFile("malware.exe", b"nope", content_type="application/octet-stream")
        response = self.client.post(reverse("rag:upload"), {"file": upload})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Document.objects.exists())

    def test_delete_document(self):
        upload = SimpleUploadedFile("notes.txt", b"delete me", content_type="text/plain")
        document = Document.objects.create(user=self.user, title="Notes", file=upload, size_bytes=9)
        response = self.client.post(reverse("rag:delete", args=[document.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())
