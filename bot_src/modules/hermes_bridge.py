"""Private, owner-only persistence and HTTP client for the Hermes agent."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import aiohttp

try:
    from bot_src import config as _config
except ModuleNotFoundError as import_error:
    # bot_main adds bot_src to sys.path; importing this module as a top-level
    # module in that mode uses `import config` instead of `bot_src.config`.
    if import_error.name not in {"bot_src", "bot_src.config"}:
        _config = None
    else:
        try:
            import config as _config
        except Exception:  # Configuration errors must never grant access.
            _config = None
except Exception:  # Configuration errors must never grant access.
    _config = None


MODEL_DESCRIPTIONS = {
    "claude-sonnet-5": (
        "recommended default — balances quality, speed, and cost for coding, "
        "research, and tool use"
    ),
    "claude-opus-5": "strongest reasoning; slower and most expensive",
    "claude-haiku-4-5": (
        "fastest and cheapest for quick questions and simple edits; not for complex runs"
    ),
}
MODEL_LABELS = {
    "claude-sonnet-5": "Claude Sonnet 5",
    "claude-opus-5": "Claude Opus 5",
    "claude-haiku-4-5": "Claude Haiku 4.5",
}
DEFAULT_MODEL = "claude-sonnet-5"
HERMES_URL = "http://127.0.0.1:8642/v1/responses"
HERMES_HMAC_CONTEXT = b"onichan-hermes-api-v1"
REQUEST_TIMEOUT_SECONDS = 600
MAX_PROMPT_UTF8_BYTES = 8 * 1024


class HermesServiceError(Exception):
    """An error with a safe, user-facing message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message


def _strict_owner_id(value: Any) -> int | None:
    """Return a configured positive Telegram ID, or fail closed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        try:
            owner_id = int(value)
        except ValueError:
            return None
        return owner_id if owner_id > 0 else None
    return None


def _configured_owner_id() -> int | None:
    if _config is None:
        return None
    return _strict_owner_id(getattr(_config, "OWNER_ID", None))


def _uuid_string() -> str:
    return str(uuid.uuid4())


class HermesBridge:
    """Hermes HTTP bridge and dedicated atomic JSON state store.

    Only this module's state file is read. In particular, user config and
    credential JSON files are never opened or consulted.
    """

    def __init__(
        self,
        *,
        database_dir: str | os.PathLike[str] | None = None,
        owner_id: Any = None,
        session_secret: str | None = None,
        api_url: str = HERMES_URL,
    ) -> None:
        configured_database_dir = (
            getattr(_config, "DATABASE_DIR", None) if _config is not None else None
        )
        self.database_dir = Path(database_dir or configured_database_dir or "data")
        self.state_path = self.database_dir / "hermes_agent_state.json"
        self.owner_id = (
            _configured_owner_id() if owner_id is None else _strict_owner_id(owner_id)
        )
        self.session_secret = (
            os.environ.get("SESSION_SECRET", "")
            if session_secret is None
            else session_secret
        )
        self.api_url = api_url
        self._busy_chats: set[int] = set()

    def is_private_owner(self, user_id: Any, chat_type: Any) -> bool:
        """Require exact OWNER_ID equality and a Telegram private chat."""
        return (
            self._is_configured_owner(user_id)
            and chat_type == "private"
        )

    def _is_configured_owner(self, owner_id: Any) -> bool:
        return (
            self.owner_id is not None
            and isinstance(owner_id, int)
            and not isinstance(owner_id, bool)
            and owner_id == self.owner_id
        )

    def try_start_chat(self, chat_id: Any) -> bool:
        """Atomically claim one chat for a single in-flight request."""
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            return False
        if chat_id in self._busy_chats:
            return False
        self._busy_chats.add(chat_id)
        return True

    def finish_chat(self, chat_id: Any) -> None:
        if isinstance(chat_id, int) and not isinstance(chat_id, bool):
            self._busy_chats.discard(chat_id)

    def is_chat_busy(self, chat_id: Any) -> bool:
        return isinstance(chat_id, int) and chat_id in self._busy_chats

    def _new_state(self, model: str = DEFAULT_MODEL) -> dict[str, Any]:
        return {
            "model": model,
            "session_id": _uuid_string(),
            "conversation_id": _uuid_string(),
            "previous_response_id": None,
        }

    def get_model_inventory(self) -> list[dict[str, str]]:
        """Return only explicitly supported models; never discover/fallback providers."""
        return [
            {
                "id": model_id,
                "name": MODEL_LABELS[model_id],
                "description": description,
            }
            for model_id, description in MODEL_DESCRIPTIONS.items()
        ]

    def health(self) -> dict[str, Any]:
        """Report local bridge configuration health without leaking credentials."""
        secret_configured = (
            isinstance(self.session_secret, str) and bool(self.session_secret)
        )
        owner_configured = self.owner_id is not None
        return {
            "healthy": owner_configured and secret_configured,
            "owner_configured": owner_configured,
            "session_secret_configured": secret_configured,
            "gateway_configured": bool(self.api_url),
        }

    def _load_all_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"owners": {}}
        try:
            with self.state_path.open("r", encoding="utf-8") as state_file:
                data = json.load(state_file)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HermesServiceError(
                "Agent settings are unavailable. Contact the administrator."
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("owners"), dict):
            raise HermesServiceError(
                "Agent settings are unavailable. Contact the administrator."
            )
        return data

    def _validated_state(self, candidate: Any) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise HermesServiceError(
                "Agent settings are unavailable. Contact the administrator."
            )
        model = candidate.get("model")
        session_id = candidate.get("session_id")
        conversation_id = candidate.get("conversation_id")
        previous_response_id = candidate.get("previous_response_id")
        try:
            valid_session = str(uuid.UUID(session_id)) == session_id
            valid_conversation = str(uuid.UUID(conversation_id)) == conversation_id
        except (ValueError, TypeError, AttributeError):
            valid_session = valid_conversation = False
        if (
            model not in MODEL_DESCRIPTIONS
            or not valid_session
            or not valid_conversation
            or (
                previous_response_id is not None
                and not isinstance(previous_response_id, str)
            )
        ):
            raise HermesServiceError(
                "Agent settings are unavailable. Contact the administrator."
            )
        return {
            "model": model,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "previous_response_id": previous_response_id,
        }

    def _write_all_state(self, data: dict[str, Any]) -> None:
        temporary_path: str | None = None
        try:
            self.database_dir.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=".hermes_agent_state.",
                suffix=".tmp",
                dir=self.database_dir,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
                json.dump(data, state_file, ensure_ascii=False, separators=(",", ":"))
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary_path, self.state_path)
            temporary_path = None
        except (OSError, TypeError, ValueError) as exc:
            raise HermesServiceError(
                "Agent settings could not be saved. Contact the administrator."
            ) from exc
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    def get_owner_state(self, owner_id: int) -> dict[str, Any]:
        if not self._is_configured_owner(owner_id):
            raise HermesServiceError("This agent is owner-only.")
        data = self._load_all_state()
        owner_key = str(owner_id)
        if owner_key not in data["owners"]:
            state = self._new_state()
            data["owners"][owner_key] = state
            self._write_all_state(data)
            return dict(state)
        return self._validated_state(data["owners"][owner_key])

    def set_model(self, owner_id: int, model: str) -> dict[str, Any]:
        if not self._is_configured_owner(owner_id):
            raise HermesServiceError("This agent is owner-only.")
        if model not in MODEL_DESCRIPTIONS:
            raise HermesServiceError("That agent model is not available.")
        data = self._load_all_state()
        is_new_owner_state = str(owner_id) not in data["owners"]
        state = self._state_for_mutation(data, owner_id)
        if is_new_owner_state or state["model"] != model:
            # A model change starts a fresh session and cannot reuse old history.
            state = self._new_state(model)
            data["owners"][str(owner_id)] = state
            self._write_all_state(data)
        return dict(state)

    def new_conversation(self, owner_id: int, *, reset_model: bool = False) -> dict[str, Any]:
        if not self._is_configured_owner(owner_id):
            raise HermesServiceError("This agent is owner-only.")
        data = self._load_all_state()
        old_state = self._state_for_mutation(data, owner_id)
        model = DEFAULT_MODEL if reset_model else old_state["model"]
        state = self._new_state(model)
        data["owners"][str(owner_id)] = state
        self._write_all_state(data)
        return dict(state)

    def _state_for_mutation(
        self, data: dict[str, Any], owner_id: int
    ) -> dict[str, Any]:
        if not self._is_configured_owner(owner_id):
            raise HermesServiceError("This agent is owner-only.")
        key = str(owner_id)
        if key not in data["owners"]:
            state = self._new_state()
            data["owners"][key] = state
            return state
        return self._validated_state(data["owners"][key])

    def _authorization_key(self) -> str:
        if not isinstance(self.session_secret, str) or not self.session_secret:
            raise HermesServiceError(
                "Agent service is not configured. Contact the administrator."
            )
        return hmac.new(
            self.session_secret.encode("utf-8"),
            HERMES_HMAC_CONTEXT,
            hashlib.sha256,
        ).hexdigest()

    async def ask(self, owner_id: int, prompt: str) -> str:
        if not self._is_configured_owner(owner_id):
            raise HermesServiceError("This agent is owner-only.")
        if len(prompt.encode("utf-8")) > MAX_PROMPT_UTF8_BYTES:
            raise HermesServiceError("Your prompt must be 8 KB or smaller.")
        state = self.get_owner_state(owner_id)
        payload: dict[str, Any] = {
            "provider": "anthropic",
            "model": state["model"],
            "input": prompt,
            "conversation": state["conversation_id"],
            "stream": False,
        }
        # Hermes continues state through its named conversation. The upstream
        # Responses API rejects requests that combine conversation and
        # previous_response_id, so never send the latter.
        headers = {
            "Authorization": f"Bearer {self._authorization_key()}",
            "X-Hermes-Session-Key": state["session_id"],
            "Content-Type": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                ) as response:
                    if response.status in (401, 403):
                        raise HermesServiceError(
                            "Agent authentication failed. Contact the administrator."
                        )
                    if response.status < 200 or response.status >= 300:
                        raise HermesServiceError(
                            "Agent service returned an error. Please try again later."
                        )
                    try:
                        response_data = await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, json.JSONDecodeError, ValueError):
                        raise HermesServiceError(
                            "Agent service returned an invalid response."
                        ) from None
        except HermesServiceError:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
            raise HermesServiceError(
                "Agent service is unavailable or timed out. Please try again later."
            ) from None

        if not isinstance(response_data, dict):
            raise HermesServiceError("Agent service returned an invalid response.")
        if (
            isinstance(response_data.get("status"), str)
            and response_data["status"].lower() == "failed"
        ):
            raise HermesServiceError(
                "Agent request failed. Please try again later."
            )
        answer = self._response_text(response_data)
        if not answer:
            raise HermesServiceError("Agent service returned an invalid response.")

        response_id = response_data.get("id")
        if response_id is not None and not isinstance(response_id, str):
            raise HermesServiceError("Agent service returned an invalid response.")
        data = self._load_all_state()
        saved_state = self._state_for_mutation(data, owner_id)
        # Do not allow stale response IDs to be reused if the gateway omits one.
        saved_state["previous_response_id"] = response_id
        data["owners"][str(owner_id)] = saved_state
        self._write_all_state(data)
        return answer

    @staticmethod
    def _response_text(response_data: dict[str, Any]) -> str:
        output = response_data.get("output")
        if not isinstance(output, list):
            return ""
        text_parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if (
                    isinstance(content_item, dict)
                    and content_item.get("type") == "output_text"
                    and isinstance(content_item.get("text"), str)
                ):
                    text_parts.append(content_item["text"])
        return "\n".join(part for part in text_parts if part)