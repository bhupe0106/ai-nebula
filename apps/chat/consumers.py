import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ValidationError

from apps.usage.services import aquota_payload

from .models import Conversation
from .services import (
    MAX_MESSAGE_CHARS,
    QuotaExceeded,
    arender_message,
    prepare_turn,
    run_turn,
    serialize_message,
)

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """One authenticated socket per open conversation."""

    async def connect(self):
        self._alive = True
        self._busy = False
        self._stop = False
        self.user = self.scope.get("user")

        if self.user is None or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        try:
            self.conversation = await Conversation.objects.select_related("user").aget(
                id=self.conversation_id, user_id=self.user.id
            )
        except (Conversation.DoesNotExist, ValidationError, ValueError):
            await self.close(code=4404)
            return

        await self.accept()
        await self._send(
            {
                "type": "ready",
                "conversation_id": str(self.conversation.id),
                "quota": await aquota_payload(self.user),
            }
        )

    async def disconnect(self, code):
        self._alive = False
        self._stop = True

    async def _send(self, payload: dict) -> None:
        if not self._alive:
            return
        try:
            await self.send_json(payload)
        except Exception:  # socket closed between checks
            self._alive = False

    async def receive_json(self, content, **kwargs):
        if not self._alive or not isinstance(content, dict):
            return

        action = str(content.get("action") or "send").lower()
        if action == "ping":
            await self._send({"type": "pong"})
            return
        if action == "stop":
            self._stop = True
            return
        if action != "send":
            await self._send({"type": "error", "message": "Unknown action."})
            return
        if self._busy:
            await self._send(
                {"type": "error", "message": "A reply is already streaming."}
            )
            return

        text = str(content.get("message") or "").strip()
        if not text:
            return
        if len(text) > MAX_MESSAGE_CHARS:
            await self._send(
                {
                    "type": "error",
                    "message": f"Messages are limited to {MAX_MESSAGE_CHARS} characters.",
                }
            )
            return

        self._busy = True
        self._stop = False
        try:
            try:
                turn = await prepare_turn(self.conversation, text)
            except QuotaExceeded as exc:
                await self._send(
                    {"type": "error", "message": str(exc), "code": "quota"}
                )
                return
            except ValueError as exc:
                await self._send({"type": "error", "message": str(exc)})
                return
            except Exception:
                logger.exception("Could not prepare turn for %s", self.conversation_id)
                await self._send(
                    {
                        "type": "error",
                        "message": "Could not start the reply. Please try again.",
                    }
                )
                return

            await self._send(
                {
                    "type": "turn_start",
                    "user_html": await arender_message(turn.user, self.user),
                    "user_message": serialize_message(turn.user),
                    "title": turn.conversation.title,
                }
            )

            async for event in run_turn(turn, should_stop=lambda: self._stop):
                if event.delta:
                    await self._send({"type": "token", "content": event.delta})
                if event.done and event.message is not None:
                    await self._send(
                        {
                            "type": "done",
                            "message": serialize_message(event.message),
                            "html": await arender_message(event.message, self.user),
                            "error": event.error,
                            "stopped": event.stopped,
                            "quota": await aquota_payload(self.user),
                        }
                    )
        except Exception:
            logger.exception("WebSocket chat failure in %s", self.conversation_id)
            await self._send(
                {
                    "type": "error",
                    "message": "The connection hit an unexpected error. Please retry.",
                }
            )
        finally:
            self._busy = False
