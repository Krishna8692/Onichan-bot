"""
Pyrogram-based uploader for sending large files (>50MB) directly in Telegram chat.

Telegram's HTTP Bot API caps file uploads at 50MB. Pyrogram talks to Telegram
via MTProto (the same protocol the official apps use), so a bot with API_ID +
API_HASH can send files up to 2GB natively.

Required environment variables:
- TG_API_ID — integer, from https://my.telegram.org
- TG_API_HASH — string, from https://my.telegram.org
- BOT_TOKEN — same token already used by python-telegram-bot
"""

import os
import asyncio
from typing import Optional

_client = None
_client_lock = asyncio.Lock()
_init_attempted = False
_init_error: Optional[str] = None


def is_configured() -> bool:
    """Return True if TG_API_ID, TG_API_HASH, and BOT_TOKEN are all present."""
    return bool(
        os.environ.get("TG_API_ID")
        and os.environ.get("TG_API_HASH")
        and os.environ.get("BOT_TOKEN")
    )


def get_init_error() -> Optional[str]:
    return _init_error


async def get_client():
    """Lazily start a single shared Pyrogram client. Returns None if unavailable."""
    global _client, _init_attempted, _init_error

    if not is_configured():
        return None

    async with _client_lock:
        if _client is not None:
            return _client
        if _init_attempted and _init_error:
            return None

        _init_attempted = True
        try:
            from pyrogram import Client  # type: ignore
        except Exception as e:
            _init_error = f"pyrogram import failed: {e}"
            print(f"[pyro_uploader] {_init_error}")
            return None

        try:
            api_id = int(os.environ["TG_API_ID"])
            api_hash = os.environ["TG_API_HASH"]
            bot_token = os.environ["BOT_TOKEN"]

            session_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "..", "data"
            )
            os.makedirs(session_dir, exist_ok=True)

            client = Client(
                name="onichan_uploader",
                api_id=api_id,
                api_hash=api_hash,
                bot_token=bot_token,
                workdir=session_dir,
                in_memory=False,
                no_updates=True,  # we don't process updates here, only upload
            )
            await client.start()
            _client = client
            print("[pyro_uploader] ✅ Pyrogram client started (2GB upload enabled)")
            return _client
        except Exception as e:
            _init_error = str(e)
            print(f"[pyro_uploader] start failed: {e}")
            return None


async def send_video_direct(
    chat_id: int,
    file_path: str,
    caption: str = "",
    duration: Optional[int] = None,
    title: Optional[str] = None,
    progress_callback=None,
) -> bool:
    """
    Send a video file (any size up to 2GB) directly into the chat via MTProto.
    Returns True on success.
    """
    client = await get_client()
    if client is None:
        return False

    try:
        kwargs = {
            "chat_id": chat_id,
            "video": file_path,
            "caption": caption[:1024] if caption else None,
            "parse_mode": _get_html_parse_mode(),
            "supports_streaming": True,
        }
        if duration:
            kwargs["duration"] = int(duration)
        if progress_callback:
            kwargs["progress"] = progress_callback

        await client.send_video(**kwargs)
        return True
    except Exception as e:
        print(f"[pyro_uploader] send_video failed: {e}")
        return False


async def send_document_direct(
    chat_id: int,
    file_path: str,
    caption: str = "",
    progress_callback=None,
) -> bool:
    """Send any file as a document up to 2GB."""
    client = await get_client()
    if client is None:
        return False

    try:
        kwargs = {
            "chat_id": chat_id,
            "document": file_path,
            "caption": caption[:1024] if caption else None,
            "parse_mode": _get_html_parse_mode(),
        }
        if progress_callback:
            kwargs["progress"] = progress_callback

        await client.send_document(**kwargs)
        return True
    except Exception as e:
        print(f"[pyro_uploader] send_document failed: {e}")
        return False


def _get_html_parse_mode():
    try:
        from pyrogram.enums import ParseMode  # type: ignore
        return ParseMode.HTML
    except Exception:
        return None


async def stop():
    """Stop the Pyrogram client cleanly (used during shutdown)."""
    global _client
    if _client is not None:
        try:
            await _client.stop()
        except Exception:
            pass
        _client = None
