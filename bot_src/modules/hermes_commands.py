"""Telegram /agent command and narrowly scoped Hermes model callbacks."""

from __future__ import annotations

import html
import re
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler

from bot_src.modules.hermes_bridge import (
    MAX_PROMPT_UTF8_BYTES,
    MODEL_DESCRIPTIONS,
    MODEL_LABELS,
    HermesBridge,
    HermesServiceError,
)


_DEFAULT_BRIDGE = HermesBridge()
_CALLBACK_PATTERN = (
    r"^hermes:(?:model:(?:claude-sonnet-5|claude-opus-5|claude-haiku-4-5)|new|reset)$"
)
_MODEL_CALLBACK = re.compile(r"^hermes:model:(claude-sonnet-5|claude-opus-5|claude-haiku-4-5)$")


def _is_authorized(update: Any, bridge: HermesBridge) -> bool:
    user = getattr(update, "effective_user", None)
    chat = getattr(update, "effective_chat", None)
    return bridge.is_private_owner(
        getattr(user, "id", None),
        getattr(chat, "type", None),
    )


def _model_menu(state: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["Choose a model for this private agent conversation:"]
    lines.append(
        "Gateway tools are restricted to todo and memory; shell, file, and browser access are unavailable."
    )
    buttons = []
    selected_model = state["model"]
    for model, description in MODEL_DESCRIPTIONS.items():
        selected = model == selected_model
        check = "✓ " if selected else ""
        lines.append(f"{check}{MODEL_LABELS[model]} — {description}")
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{check}{MODEL_LABELS[model]}",
                    callback_data=f"hermes:model:{model}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("New conversation", callback_data="hermes:new")]
    )
    buttons.append([InlineKeyboardButton("Reset settings", callback_data="hermes:reset")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def split_telegram_html_chunks(text: str, max_utf16_units: int = 3999) -> list[str]:
    """Escape and split text without exceeding Telegram's UTF-16 chunk limit."""
    if max_utf16_units < 1 or max_utf16_units >= 4000:
        raise ValueError("Telegram chunk size must be between 1 and 3999 UTF-16 units")
    chunks: list[str] = []
    current: list[str] = []
    used_units = 0
    for character in text:
        escaped_character = html.escape(character, quote=True)
        units = len(escaped_character.encode("utf-16-le")) // 2
        if current and used_units + units > max_utf16_units:
            chunks.append("".join(current))
            current = []
            used_units = 0
        current.append(escaped_character)
        used_units += units
    if current:
        chunks.append("".join(current))
    return chunks or [""]


def _prompt_from_update(update: Any, context: Any) -> str:
    args = getattr(context, "args", None)
    if args:
        return " ".join(str(part) for part in args)
    message = getattr(update, "effective_message", None)
    text = getattr(message, "text", "") or ""
    return re.sub(r"^/agent(?:@\w+)?(?:\s+|$)", "", text, count=1).strip()


async def _deny_command(update: Any) -> None:
    message = getattr(update, "effective_message", None)
    if message is not None:
        await message.reply_text("This command is available only to the owner in a private chat.")


async def _run_agent(update: Any, context: Any, bridge: HermesBridge) -> None:
    if not _is_authorized(update, bridge):
        await _deny_command(update)
        return

    owner_id = update.effective_user.id
    chat_id = update.effective_chat.id
    prompt = _prompt_from_update(update, context)
    if not prompt:
        try:
            state = bridge.get_owner_state(owner_id)
        except HermesServiceError as exc:
            await update.effective_message.reply_text(exc.user_message)
            return
        text, keyboard = _model_menu(state)
        await update.effective_message.reply_text(text, reply_markup=keyboard)
        return

    try:
        prompt_size = len(prompt.encode("utf-8"))
    except UnicodeEncodeError:
        await update.effective_message.reply_text("Your prompt must be valid UTF-8 and 8 KB or smaller.")
        return
    if prompt_size > MAX_PROMPT_UTF8_BYTES:
        await update.effective_message.reply_text("Your prompt must be 8 KB or smaller.")
        return

    if not bridge.try_start_chat(chat_id):
        await update.effective_message.reply_text("Agent is already working in this private chat.")
        return

    status_message = None
    try:
        status_message = await update.effective_message.reply_text("Agent is working…")
        try:
            answer = await bridge.ask(owner_id, prompt)
        except HermesServiceError as exc:
            await status_message.edit_text(exc.user_message)
            return
        except Exception:
            await status_message.edit_text(
                "Agent request failed. Please try again later."
            )
            return
        chunks = split_telegram_html_chunks(answer)
        await status_message.edit_text(chunks[0], parse_mode="HTML")
        for chunk in chunks[1:]:
            await update.effective_message.reply_text(chunk, parse_mode="HTML")
    finally:
        bridge.finish_chat(chat_id)


async def agent_command(update: Any, context: Any) -> None:
    """Handle /agent using the module's configured bridge."""
    await _run_agent(update, context, _DEFAULT_BRIDGE)


async def _run_callback(update: Any, context: Any, bridge: HermesBridge) -> None:
    query = getattr(update, "callback_query", None)
    if query is None:
        return
    if not _is_authorized(update, bridge):
        await query.answer("This agent is owner-only in private chat.", show_alert=True)
        return

    chat_id = update.effective_chat.id
    if bridge.is_chat_busy(chat_id):
        await query.answer("Agent is working; settings cannot be changed yet.", show_alert=True)
        return

    data = getattr(query, "data", "")
    try:
        if _MODEL_CALLBACK.fullmatch(data or ""):
            model = _MODEL_CALLBACK.fullmatch(data).group(1)
            state = bridge.set_model(update.effective_user.id, model)
            text, keyboard = _model_menu(state)
            await query.answer("Model selected.")
            await query.edit_message_text(text, reply_markup=keyboard)
        elif data == "hermes:new":
            state = bridge.new_conversation(update.effective_user.id)
            text, keyboard = _model_menu(state)
            await query.answer("Started a new conversation.")
            await query.edit_message_text(text, reply_markup=keyboard)
        elif data == "hermes:reset":
            state = bridge.new_conversation(update.effective_user.id, reset_model=True)
            text, keyboard = _model_menu(state)
            await query.answer("Settings reset; conversation history cleared.")
            await query.edit_message_text(text, reply_markup=keyboard)
        else:
            await query.answer("Unsupported agent action.", show_alert=True)
    except HermesServiceError as exc:
        await query.answer(exc.user_message, show_alert=True)
    except Exception:
        await query.answer(
            "Agent settings could not be updated. Please try again later.",
            show_alert=True,
        )


async def agent_callback(update: Any, context: Any) -> None:
    """Handle only the supported hermes: inline keyboard callbacks."""
    await _run_callback(update, context, _DEFAULT_BRIDGE)


def get_hermes_handlers(bridge: HermesBridge | None = None) -> list[Any]:
    """Return the /agent and hermes:-only handlers for application registration."""
    if bridge is None or bridge is _DEFAULT_BRIDGE:
        command_callback = agent_command
        inline_callback = agent_callback
    else:
        async def command_callback(update: Any, context: Any) -> None:
            await _run_agent(update, context, bridge)

        async def inline_callback(update: Any, context: Any) -> None:
            await _run_callback(update, context, bridge)

    return [
        CommandHandler("agent", command_callback, block=False),
        CallbackQueryHandler(inline_callback, pattern=_CALLBACK_PATTERN, block=False),
    ]