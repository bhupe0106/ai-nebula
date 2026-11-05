from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.chat.models import Conversation
from apps.llm import reset_llm_cache
from apps.rag.models import Document
from apps.usage.services import record_usage

User = get_user_model()


@override_settings(LLM_PROVIDER="mock", MOCK_LLM_DELAY=0, RAG_MIN_SCORE=0.99)
class APITests(TestCase):
    def setUp(self):
        reset_llm_cache()
        self.user = User.objects.create_user(email="api@example.com", password="password12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        reset_llm_cache()

    def test_requires_authentication(self):
        client = APIClient()
        response = client.get("/api/v1/conversations/")
        self.assertIn(response.status_code, (401, 403))

    def test_jwt_token_obtain(self):
        client = APIClient()
        response = client.post(
            reverse("api:token_obtain_pair"),
            {"email": "api@example.com", "password": "password12345"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_conversation_crud(self):
        response = self.client.post(
            reverse("api:conversation-list"),
            {"title": "API chat", "temperature": 0.5},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        conversation_id = response.data["id"]
        self.assertEqual(response.data["title"], "API chat")

        detail = self.client.get(
                reverse("api:conversation-detail", args=[conversation_id])
        )
        self.assertEqual(detail.status_code, 200)

        patched = self.client.patch(
            reverse("api:conversation-detail", args=[conversation_id]),
            {"title": "Renamed"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["title"], "Renamed")

    def test_send_message_and_list(self):
        conversation = Conversation.objects.create(user=self.user, title="API")
        response = self.client.post(
            reverse("api:conversation-messages", args=[conversation.pk]),
            {"content": "Hello API"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["assistant_message"]["role"], "assistant")
        self.assertIn("Hello API", response.data["assistant_message"]["content"])

        listing = self.client.get(
            reverse("api:conversation-messages", args=[conversation.pk])
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 2)

    def test_quota_exceeded_returns_429(self):
        conversation = Conversation.objects.create(user=self.user)
        self.user.profile.monthly_token_quota = 1
        self.user.profile.save(update_fields=["monthly_token_quota"])
        record_usage(user=self.user, prompt_tokens=1, completion_tokens=1)
        response = self.client.post(
            reverse("api:conversation-messages", args=[conversation.pk]),
            {"content": "blocked"},
            format="json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "quota_exceeded")

    def test_cannot_access_other_users_conversation(self):
        other = User.objects.create_user(email="other-api@example.com", password="password12345")
        conversation = Conversation.objects.create(user=other)
        response = self.client.get(
            reverse("api:conversation-detail", args=[conversation.pk])
        )
        self.assertEqual(response.status_code, 404)

    @patch("apps.api.views.queue_ingestion")
    def test_document_upload(self, queue_ingestion):
        queue_ingestion.side_effect = lambda document: document
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("api.txt", b"API document", content_type="text/plain")
        response = self.client.post(
            reverse("api:document-list"),
            {"file": upload, "title": "API doc"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "API doc")
        self.assertTrue(Document.objects.filter(user=self.user).exists())

    def test_me_and_usage(self):
        me = self.client.get(reverse("api:me"))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], "api@example.com")
        usage = self.client.get(reverse("api:usage"))
        self.assertEqual(usage.status_code, 200)
        self.assertIn("quota", usage.data)
