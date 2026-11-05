from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.llm import reset_llm_cache
from apps.usage.models import UsageEvent
from apps.usage.services import record_usage

from .models import Conversation, Message
from .routing import websocket_urlpatterns
from .services import (
    QuotaExceeded,
    derive_title,
    generate_reply,
    prepare_turn,
    serialize_message,
)

User = get_user_model()

MOCK_SETTINGS = dict(LLM_PROVIDER="mock", MOCK_LLM_DELAY=0, RAG_MIN_SCORE=0.99)


@override_settings(**MOCK_SETTINGS)
class ChatServiceTests(TestCase):
    def setUp(self):
        reset_llm_cache()
        self.user = User.objects.create_user(email="chat@example.com", password="password12345")
        self.conversation = Conversation.objects.create(user=self.user)

    def tearDown(self):
        reset_llm_cache()

    def test_derive_title(self):
        self.assertEqual(derive_title(""), "New chat")
        self.assertEqual(derive_title("Hello there"), "Hello there")
        self.assertTrue(derive_title("x" * 100).endswith("…"))
        self.assertLessEqual(len(derive_title("x" * 100)), 60)

    def test_prepare_turn_saves_message_and_title(self):
        turn = async_to_sync(prepare_turn)(self.conversation, "Explain embeddings")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "Explain embeddings")
        self.assertEqual(turn.user.role, Message.Role.USER)
        self.assertEqual(turn.prompt[-1].content, "Explain embeddings")
        self.assertEqual(turn.prompt[0].role, "system")
        self.assertTrue(Message.objects.filter(conversation=self.conversation).exists())

    def test_generate_reply_streams_and_records_usage(self):
        message = generate_reply(self.conversation, "Hello assistant")
        self.assertEqual(message.role, Message.Role.ASSISTANT)
        self.assertIn("Hello assistant", message.content)
        self.assertGreater(message.completion_tokens, 0)
        self.assertFalse(message.error)
        self.assertTrue(
            UsageEvent.objects.filter(
                user=self.user, conversation=self.conversation, kind=UsageEvent.Kind.CHAT
            ).exists()
        )

    def test_quota_exceeded_blocks_turn(self):
        self.user.profile.monthly_token_quota = 10
        self.user.profile.save(update_fields=["monthly_token_quota"])
        record_usage(user=self.user, prompt_tokens=10, completion_tokens=1)
        with self.assertRaises(QuotaExceeded):
            generate_reply(self.conversation, "This must be blocked")
        self.assertFalse(self.conversation.messages.exists())

    def test_serialize_message_shape(self):
        message = generate_reply(self.conversation, "Serialize me")
        payload = serialize_message(message)
        self.assertEqual(payload["role"], "assistant")
        self.assertIn("total_tokens", payload)
        self.assertIn("citations", payload)


@override_settings(**MOCK_SETTINGS)
class ChatViewTests(TestCase):
    def setUp(self):
        reset_llm_cache()
        self.user = User.objects.create_user(email="views@example.com", password="password12345")
        self.other = User.objects.create_user(email="other@example.com", password="password12345")
        self.conversation = Conversation.objects.create(user=self.user, title="Test chat")
        self.client.login(email="views@example.com", password="password12345")

    def tearDown(self):
        reset_llm_cache()

    def test_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("chat:list"))
        self.assertEqual(response.status_code, 302)

    def test_list_renders_own_conversations(self):
        Conversation.objects.create(user=self.other, title="Secret")
        response = self.client.get(reverse("chat:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test chat")
        self.assertNotContains(response, "Secret")

    def test_create_conversation(self):
        response = self.client.post(reverse("chat:create"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 2)

    def test_detail_is_owner_only(self):
        other_conversation = Conversation.objects.create(user=self.other)
        response = self.client.get(
            reverse("chat:detail", args=[other_conversation.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_http_fallback_send_creates_pair(self):
        response = self.client.post(
            reverse("chat:send", args=[self.conversation.pk]),
            {"content": "Hello from the fallback"},
        )
        self.assertEqual(response.status_code, 302)
        roles = list(
            self.conversation.messages.values_list("role", flat=True)
        )
        self.assertEqual(roles, ["user", "assistant"])

    def test_blank_message_is_rejected(self):
        response = self.client.post(
            reverse("chat:send", args=[self.conversation.pk]), {"content": "   "}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.conversation.messages.exists())

    def test_settings_update(self):
        response = self.client.post(
            reverse("chat:settings", args=[self.conversation.pk]),
            {
                "title": "Renamed",
                "model": "",
                "temperature": "0.3",
                "system_prompt": "Be brief.",
                "use_documents": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "Renamed")
        self.assertEqual(self.conversation.temperature, 0.3)
        self.assertTrue(self.conversation.use_documents)

    def test_archive_toggle(self):
        self.client.post(reverse("chat:archive", args=[self.conversation.pk]))
        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_archived)
        self.client.post(reverse("chat:archive", args=[self.conversation.pk]))
        self.conversation.refresh_from_db()
        self.assertFalse(self.conversation.is_archived)

    def test_clear_messages(self):
        generate_reply(self.conversation, "clear me")
        self.client.post(reverse("chat:clear", args=[self.conversation.pk]))
        self.assertFalse(self.conversation.messages.exists())

    def test_delete_conversation(self):
        self.client.post(reverse("chat:delete", args=[self.conversation.pk]))
        self.assertFalse(Conversation.objects.filter(pk=self.conversation.pk).exists())

    def test_export_json(self):
        generate_reply(self.conversation, "export me")
        response = self.client.get(reverse("chat:export", args=[self.conversation.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment", response["Content-Disposition"])
        payload = response.json()
        self.assertEqual(payload["title"], "Test chat")
        self.assertEqual(len(payload["messages"]), 2)

    def test_search_matches_message_content(self):
        generate_reply(self.conversation, "a unique needle phrase")
        response = self.client.get(reverse("chat:search"), {"q": "needle"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test chat")

    def test_messages_partial(self):
        generate_reply(self.conversation, "partial")
        response = self.client.get(reverse("chat:messages", args=[self.conversation.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "partial")

    def test_quota_exceeded_shows_error(self):
        self.user.profile.monthly_token_quota = 1
        self.user.profile.save(update_fields=["monthly_token_quota"])
        record_usage(user=self.user, prompt_tokens=1, completion_tokens=1)
        response = self.client.post(
            reverse("chat:send", args=[self.conversation.pk]), {"content": "blocked"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.conversation.messages.exists())


@override_settings(**MOCK_SETTINGS)
class WebSocketTests(TransactionTestCase):
    """Exercise the real consumer contract end to end."""

    def setUp(self):
        reset_llm_cache()
        self.user = User.objects.create_user(
            email="socket@example.com", password="password12345"
        )
        self.conversation = Conversation.objects.create(user=self.user, title="Socket chat")

    def tearDown(self):
        reset_llm_cache()

    def _communicator(self):
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/chat/{self.conversation.pk}/",
        )
        communicator.scope["user"] = self.user
        return communicator

    async def test_socket_streams_a_reply(self):
        communicator = self._communicator()
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        ready = await communicator.receive_json_from()
        self.assertEqual(ready["type"], "ready")
        self.assertIn("quota", ready)

        await communicator.send_json_to({"action": "ping"})
        self.assertEqual((await communicator.receive_json_from())["type"], "pong")

        await communicator.send_json_to({"action": "send", "message": "Hello socket"})
        kinds = []
        while True:
            event = await communicator.receive_json_from()
            kinds.append(event["type"])
            if event["type"] in ("done", "error"):
                break

        self.assertIn("turn_start", kinds)
        self.assertIn("token", kinds)
        self.assertEqual(kinds[-1], "done")
        self.assertIn("Hello socket", event["message"]["content"])

        await communicator.disconnect()

    async def test_socket_rejects_unknown_action(self):
        communicator = self._communicator()
        await communicator.connect()
        await communicator.receive_json_from()
        await communicator.send_json_to({"action": "dance"})
        event = await communicator.receive_json_from()
        self.assertEqual(event["type"], "error")
        await communicator.disconnect()
