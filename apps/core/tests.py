from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.chat.models import Conversation, Message
from apps.rag.models import Document
from apps.usage.models import UsageEvent


class HealthTests(TestCase):
    def test_health_endpoint_is_public(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_anonymous_home_renders(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nebula")

    def test_authenticated_home_redirects_to_chat(self):
        get_user_model().objects.create_user(email="home@example.com", password="password12345")
        self.client.login(email="home@example.com", password="password12345")
        response = self.client.get(reverse("core:home"))
        self.assertRedirects(response, reverse("chat:list"))


@override_settings(LLM_PROVIDER="mock", MOCK_LLM_DELAY=0)
class PageRenderTests(TestCase):
    """Every user-facing page must render without template errors."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="pages@example.com", password="password12345"
        )
        self.conversation = Conversation.objects.create(user=self.user, title="Smoke chat")
        self.client.force_login(self.user)

    def test_public_pages_render(self):
        self.client.logout()
        for name in ("core:home", "login", "accounts:signup", "password_reset"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_authenticated_pages_render(self):
        pages = (
            reverse("chat:list"),
            reverse("chat:detail", args=[self.conversation.pk]),
            reverse("rag:library"),
            reverse("usage:dashboard"),
            reverse("accounts:profile"),
        )
        for url in pages:
            with self.subTest(page=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_detail_includes_streaming_seams(self):
        response = self.client.get(reverse("chat:detail", args=[self.conversation.pk]))
        self.assertContains(response, "data-conversation-id")
        self.assertContains(response, "js/chat.js")
        self.assertContains(response, "settings-dialog")

    def test_populated_pages_render(self):
        user_message = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content="Summarize the brief",
        )
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content="**Summary.** The brief proposes a usage tier.",
            model="mock-model",
            prompt_tokens=12,
            completion_tokens=34,
            latency_ms=120,
            metadata={"stopped": False, "citations": [{"title": "brief.pdf", "score": 0.91}]},
        )
        UsageEvent.objects.create(
            user=self.user,
            conversation=self.conversation,
            kind=UsageEvent.Kind.CHAT,
            model="mock-model",
            prompt_tokens=12,
            completion_tokens=34,
        )
        Document.objects.create(
            user=self.user,
            conversation=self.conversation,
            title="brief.pdf",
            file="documents/brief.pdf",
            size_bytes=2048,
            status=Document.Status.READY,
            chunk_count=4,
        )

        for url in (
            reverse("chat:detail", args=[self.conversation.pk]),
            reverse("chat:search") + f"?q={user_message.content.split()[0]}",
            reverse("rag:library"),
            reverse("usage:dashboard"),
        ):
            with self.subTest(page=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

        detail = self.client.get(reverse("chat:detail", args=[self.conversation.pk]))
        self.assertContains(detail, "brief.pdf")
        self.assertContains(detail, "mock-model")
        self.assertContains(detail, "source")

    def test_chat_history_does_not_shadow_flash_messages(self):
        """The transcript context must not replace Django's messages framework."""
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content="Only in the transcript",
        )
        response = self.client.post(
            reverse("chat:settings", args=[self.conversation.pk]),
            {
                "title": "Smoke chat",
                "model": "",
                "temperature": "0.7",
                "system_prompt": "",
                "use_documents": "",
            },
            follow=True,
        )
        self.assertContains(response, "Conversation settings saved.")
        self.assertContains(response, "Only in the transcript")
        self.assertNotContains(response, "User message in")
        self.assertNotContains(response, "Assistant message in")

    def test_error_pages_render(self):
        missing = self.client.get("/definitely-not-a-real-page/")
        self.assertEqual(missing.status_code, 404)
        self.assertContains(missing, "404", status_code=404)

    def test_logged_out_page_renders(self):
        response = self.client.post(reverse("logout"))
        self.assertRedirects(
            response, reverse("core:home"), fetch_redirect_response=False
        )
        landing = self.client.get(reverse("core:home"))
        self.assertContains(landing, "Nebula")
