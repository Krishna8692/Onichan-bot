import asyncio
import hashlib
import hmac
import html
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web

from bot_src.modules.hermes_bridge import (
    HERMES_HMAC_CONTEXT,
    HermesBridge,
    HermesServiceError,
    _strict_owner_id,
)
from bot_src.modules.hermes_commands import (
    get_hermes_handlers,
    split_telegram_html_chunks,
)


OWNER_ID = 784321


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.replies = []
        self.edits = []

    async def reply_text(self, text, **kwargs):
        message = FakeMessage(text)
        message.reply_markup = kwargs.get("reply_markup")
        message.parse_mode = kwargs.get("parse_mode")
        self.replies.append((text, kwargs, message))
        return message

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.edits = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


def make_update(*, user_id=OWNER_ID, chat_type="private", chat_id=OWNER_ID,
                text="", callback_data=None):
    message = FakeMessage(text)
    callback = FakeCallbackQuery(callback_data) if callback_data is not None else None
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
        effective_message=message,
        callback_query=callback,
    )


class HermesBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.requests = []
        self.response_status = 200
        self.response_body = {
            "id": "resp-first",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Hello"},
                        {"type": "text", "text": "not output text"},
                    ],
                },
                {"content": [{"type": "output_text", "text": "world"}]},
            ],
        }
        self.started = asyncio.Event()
        self.release_response = asyncio.Event()
        self.hold_response = False
        app = web.Application()
        app.router.add_post("/v1/responses", self._response_handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.bridge = HermesBridge(
            database_dir=self.temp_dir.name,
            owner_id=OWNER_ID,
            session_secret="test-session-secret",
            api_url=f"http://127.0.0.1:{port}/v1/responses",
        )
        self.command_handler, self.callback_handler = get_hermes_handlers(self.bridge)

    async def asyncTearDown(self):
        self.release_response.set()
        await self.runner.cleanup()
        self.temp_dir.cleanup()

    async def _response_handler(self, request):
        self.requests.append(
            {
                "headers": dict(request.headers),
                "payload": await request.json(),
            }
        )
        if (
            "conversation" in self.requests[-1]["payload"]
            and "previous_response_id" in self.requests[-1]["payload"]
        ):
            return web.json_response(
                {"error": {"message": "conversation and previous_response_id conflict"}},
                status=400,
            )
        self.started.set()
        if self.hold_response:
            await self.release_response.wait()
        if self.response_status == 401:
            return web.Response(status=401, text="sensitive gateway body")
        return web.json_response(self.response_body, status=self.response_status)

    async def test_strict_owner_config_and_private_command_guard(self):
        self.assertEqual(_strict_owner_id(OWNER_ID), OWNER_ID)
        self.assertEqual(_strict_owner_id(str(OWNER_ID)), OWNER_ID)
        for invalid in (None, True, 0, -1, "not-an-id", " 784321", "١٢٣"):
            self.assertIsNone(_strict_owner_id(invalid))

        outsider = make_update(user_id=OWNER_ID + 1)
        await self.command_handler.callback(outsider, SimpleNamespace(args=["secret"]))
        self.assertIn("owner", outsider.effective_message.replies[0][0].lower())
        self.assertFalse(self.bridge.state_path.exists())

        group_update = make_update(chat_type="group", text="/agent secret")
        await self.command_handler.callback(group_update, SimpleNamespace(args=["secret"]))
        self.assertIn("private chat", group_update.effective_message.replies[0][0].lower())
        self.assertFalse(self.bridge.state_path.exists())

    async def test_callback_private_owner_guard_and_narrow_handlers(self):
        handlers = get_hermes_handlers(self.bridge)
        self.assertEqual(len(handlers), 2)
        self.assertEqual(handlers[0].commands, frozenset({"agent"}))
        self.assertIn("^hermes:", handlers[1].pattern.pattern)
        self.assertFalse(handlers[0].block)
        self.assertFalse(handlers[1].block)

        outsider = make_update(user_id=OWNER_ID + 1, callback_data="hermes:new")
        await self.callback_handler.callback(outsider, SimpleNamespace())
        self.assertTrue(outsider.callback_query.answers[0][1]["show_alert"])
        self.assertFalse(self.bridge.state_path.exists())

        group_update = make_update(chat_type="group", callback_data="hermes:reset")
        await self.callback_handler.callback(group_update, SimpleNamespace())
        self.assertTrue(group_update.callback_query.answers)
        self.assertFalse(self.bridge.state_path.exists())

    async def test_model_keyboard_and_callback_reset_selected_model(self):
        menu_update = make_update(text="/agent")
        await self.command_handler.callback(menu_update, SimpleNamespace(args=[]))
        menu_text, menu_options, _ = menu_update.effective_message.replies[0]
        self.assertIn(
            "✓ Claude Sonnet 5 — recommended default", menu_text
        )
        self.assertIn("todo and memory", menu_text)
        self.assertIn("shell, file, and browser access are unavailable", menu_text)
        self.assertEqual(len(menu_options["reply_markup"].inline_keyboard), 5)

        initial = self.bridge.get_owner_state(OWNER_ID)
        selection = make_update(callback_data="hermes:model:claude-opus-5")
        await self.callback_handler.callback(selection, SimpleNamespace())
        selected = self.bridge.get_owner_state(OWNER_ID)
        self.assertEqual(selected["model"], "claude-opus-5")
        self.assertNotEqual(selected["session_id"], initial["session_id"])
        self.assertIn("✓ Claude Opus 5", selection.callback_query.edits[0][0])

        reset = make_update(callback_data="hermes:reset")
        await self.callback_handler.callback(reset, SimpleNamespace())
        reset_state = self.bridge.get_owner_state(OWNER_ID)
        self.assertEqual(reset_state["model"], "claude-sonnet-5")
        self.assertNotEqual(reset_state["conversation_id"], selected["conversation_id"])

    async def test_atomic_persistence_model_change_and_conversation_reset(self):
        original = self.bridge.get_owner_state(OWNER_ID)
        self.assertTrue(self.bridge.state_path.exists())
        self.assertEqual(set(json.loads(self.bridge.state_path.read_text())["owners"]), {str(OWNER_ID)})
        self.assertNotIn("user_configs", self.bridge.state_path.name)
        self.assertEqual(str(uuid.UUID(original["session_id"])), original["session_id"])
        self.assertEqual(str(uuid.UUID(original["conversation_id"])), original["conversation_id"])

        await self.bridge.ask(OWNER_ID, "hello")
        stored = self.bridge.get_owner_state(OWNER_ID)
        self.assertEqual(stored["previous_response_id"], "resp-first")

        changed = self.bridge.set_model(OWNER_ID, "claude-opus-5")
        self.assertEqual(changed["model"], "claude-opus-5")
        self.assertIsNone(changed["previous_response_id"])
        self.assertNotEqual(changed["session_id"], stored["session_id"])
        self.assertNotEqual(changed["conversation_id"], stored["conversation_id"])

        await self.bridge.ask(OWNER_ID, "another turn")
        await self.bridge.ask(OWNER_ID, "third turn")
        second_turn_payload = self.requests[-1]["payload"]
        self.assertEqual(second_turn_payload["conversation"], changed["conversation_id"])
        self.assertNotIn("previous_response_id", second_turn_payload)
        self.assertEqual(
            self.bridge.get_owner_state(OWNER_ID)["previous_response_id"],
            "resp-first",
        )
        before_new = self.bridge.get_owner_state(OWNER_ID)
        new_state = self.bridge.new_conversation(OWNER_ID)
        self.assertEqual(new_state["model"], "claude-opus-5")
        self.assertNotEqual(new_state["session_id"], before_new["session_id"])
        self.assertNotEqual(new_state["conversation_id"], before_new["conversation_id"])
        self.assertIsNone(new_state["previous_response_id"])
        reset = self.bridge.new_conversation(OWNER_ID, reset_model=True)
        self.assertEqual(reset["model"], "claude-sonnet-5")
        self.assertIsNone(reset["previous_response_id"])

    async def test_response_shape_hmac_headers_and_payload(self):
        state = self.bridge.set_model(OWNER_ID, "claude-haiku-4-5")
        answer = await self.bridge.ask(OWNER_ID, "What is 2 + 2?")
        self.assertEqual(answer, "Hello\nworld")
        request = self.requests[-1]
        expected_auth = hmac.new(
            b"test-session-secret",
            HERMES_HMAC_CONTEXT,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(
            request["headers"]["Authorization"], f"Bearer {expected_auth}"
        )
        self.assertEqual(request["headers"]["X-Hermes-Session-Key"], state["session_id"])
        self.assertEqual(
            request["payload"],
            {
                "provider": "anthropic",
                "model": "claude-haiku-4-5",
                "input": "What is 2 + 2?",
                "conversation": state["conversation_id"],
                "stream": False,
            },
        )
        self.assertEqual(self.bridge.get_owner_state(OWNER_ID)["previous_response_id"], "resp-first")

    async def test_auth_failure_is_generic_and_does_not_expose_gateway_body(self):
        self.response_status = 401
        with self.assertRaises(HermesServiceError) as raised:
            await self.bridge.ask(OWNER_ID, "hello")
        self.assertIn("authentication failed", raised.exception.user_message.lower())
        self.assertNotIn("sensitive", raised.exception.user_message)
        self.assertNotIn("gateway body", raised.exception.user_message)

    async def test_failed_gateway_response_does_not_return_partial_output(self):
        await self.bridge.ask(OWNER_ID, "first turn")
        self.response_body = {
            "id": "resp-failed",
            "status": "failed",
            "output": [
                {"content": [{"type": "output_text", "text": "partial sensitive output"}]}
            ],
            "error": {"message": "raw gateway failure detail"},
        }
        with self.assertRaises(HermesServiceError) as raised:
            await self.bridge.ask(OWNER_ID, "second turn")
        self.assertIn("request failed", raised.exception.user_message.lower())
        self.assertNotIn("partial", raised.exception.user_message)
        self.assertNotIn("gateway failure detail", raised.exception.user_message)
        self.assertEqual(
            self.bridge.get_owner_state(OWNER_ID)["previous_response_id"],
            "resp-first",
        )

    async def test_bridge_health_and_model_inventory_are_explicit(self):
        inventory = self.bridge.get_model_inventory()
        self.assertEqual(
            [model["id"] for model in inventory],
            ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"],
        )
        self.assertEqual(inventory[0]["name"], "Claude Sonnet 5")
        self.assertIn("tool use", inventory[0]["description"])
        self.assertTrue(self.bridge.health()["healthy"])
        unconfigured = HermesBridge(
            database_dir=self.temp_dir.name,
            owner_id=None,
            session_secret="",
        )
        self.assertFalse(unconfigured.health()["healthy"])

    async def test_missing_secret_and_prompt_limit_fail_closed(self):
        bridge_without_key = HermesBridge(
            database_dir=self.temp_dir.name,
            owner_id=OWNER_ID,
            session_secret="",
            api_url=self.bridge.api_url,
        )
        with self.assertRaises(HermesServiceError) as missing_key:
            await bridge_without_key.ask(OWNER_ID, "hello")
        self.assertIn("not configured", missing_key.exception.user_message)
        self.assertEqual(self.requests, [])

        with self.assertRaises(HermesServiceError) as oversized:
            await self.bridge.ask(OWNER_ID, "é" * 4097)
        self.assertIn("8 KB", oversized.exception.user_message)
        self.assertEqual(self.requests, [])

    async def test_utf16_html_chunks_preserve_all_text(self):
        raw = ("A<&😀" * 1900) + "tail"
        chunks = split_telegram_html_chunks(raw)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.encode("utf-16-le")) // 2 < 4000 for chunk in chunks))
        self.assertEqual(html.unescape("".join(chunks)), raw)

    async def test_busy_guard_blocks_duplicate_prompt_and_settings_change(self):
        self.hold_response = True
        first_update = make_update(text="/agent first")
        first_task = asyncio.create_task(
            self.command_handler.callback(first_update, SimpleNamespace(args=["first"]))
        )
        await asyncio.wait_for(self.started.wait(), timeout=2)

        second_update = make_update(text="/agent second")
        await self.command_handler.callback(second_update, SimpleNamespace(args=["second"]))
        self.assertIn("already working", second_update.effective_message.replies[0][0])

        state_before = self.bridge.get_owner_state(OWNER_ID)
        callback_update = make_update(callback_data="hermes:new")
        await self.callback_handler.callback(callback_update, SimpleNamespace())
        self.assertTrue(callback_update.callback_query.answers[0][1]["show_alert"])
        self.assertEqual(self.bridge.get_owner_state(OWNER_ID), state_before)

        # A separate chat is not held behind this chat's in-flight request.
        self.assertTrue(self.bridge.try_start_chat(999))
        self.bridge.finish_chat(999)
        self.release_response.set()
        await asyncio.wait_for(first_task, timeout=2)
        self.assertFalse(self.bridge.is_chat_busy(OWNER_ID))

    async def test_working_status_is_replaced_with_chunked_html_answer(self):
        update = make_update(text="/agent hello")
        await self.command_handler.callback(update, SimpleNamespace(args=["hello"]))
        status_message = update.effective_message.replies[0][2]
        self.assertEqual(update.effective_message.replies[0][0], "Agent is working…")
        self.assertEqual(status_message.edits[0][0], "Hello\nworld")
        self.assertEqual(status_message.edits[0][1]["parse_mode"], "HTML")


if __name__ == "__main__":
    unittest.main()