"""
FreakyHitter Telegram command handlers — integrated into Onichan bot.

Commands:
  /hitck   — Checkout.com Pay-by-Link hitter
  /hitad   — Adyen Pay-by-Link hitter (full 3DS)
  /hitad1  — Adyen CCN-only hitter (no CVV)
  /hitmpgs — MPGS (Mastercard Gateway) hitter
  /hitwhop — Whop.com checkout hitter
  /hitpad  — Paddle.com checkout hitter
  /hitep   — Epoch/WNU checkout hitter
  /jio     — Jio mobile recharge hitter
  /iban    — IBAN generator
  /ibancountry — List available IBAN countries
  /pick    — Pick N random lines from a card list
  /split   — Split card list into N-line chunks
  /country — Group card list by BIN country
"""

import asyncio
import io
import random
import re
import time
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

# ── Lazy imports to avoid slow startup ───────────────────────────────────────

def _parse_card(raw: str) -> Optional[dict]:
    """Parse 'CC|MM|YY|CVV' or 'CC|MM|YY' into a card dict."""
    parts = raw.strip().split("|")
    if len(parts) < 3:
        return None
    card = parts[0].strip()
    month = parts[1].strip().zfill(2)
    year = parts[2].strip()
    cvv = parts[3].strip() if len(parts) > 3 else ""
    if not card.isdigit() or len(card) < 13:
        return None
    return {"card": card, "month": month, "year": year, "cvv": cvv}


def _result_emoji(result: dict) -> str:
    if result.get("success"):
        return "✅"
    dc = (result.get("decline_code") or "").lower()
    err = (result.get("error") or "").lower()
    if "expired" in dc or "expired" in err:
        return "⏰"
    if result.get("is_live"):
        return "💳"
    return "❌"


def _format_hit_result(result: dict, gateway: str, card_raw: str, elapsed: float) -> str:
    emoji = _result_emoji(result)
    status = "Approved" if result.get("success") else "Declined"
    dc = result.get("decline_code") or result.get("error") or "Unknown"
    merchant = result.get("merchant") or "—"
    amount = result.get("amount") or "—"
    sep = "━━━━━━━━━━━━━━━━━━━━"
    return (
        f"{emoji} <b>ONICHAN • {gateway.upper()} HIT</b>\n"
        f"{sep}\n"
        f"💳 <b>Card</b>    : <code>{card_raw}</code>\n"
        f"🏷 <b>Status</b>  : <b>{status}</b>\n"
        f"🔖 <b>Code</b>    : <code>{dc}</code>\n"
        f"🏦 <b>Merchant</b>: {merchant}\n"
        f"💰 <b>Amount</b>  : {amount}\n"
        f"⏱ <b>Time</b>    : {elapsed:.1f}s\n"
        f"{sep}"
    )


def _usage(cmd: str, arg_desc: str, example: str) -> str:
    sep = "────────────────────────"
    return (
        f"🎯 <b>ONICHAN • {cmd.upper()}</b>\n\n"
        f"{sep}\n\n"
        f"📝 <b>Usage</b>: <code>{cmd} {arg_desc}</code>\n\n"
        f"📌 <b>Example</b>:\n<code>{example}</code>"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  GENERIC HITTER HELPER
# ══════════════════════════════════════════════════════════════════════════════

async def _run_hitter(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      gateway: str, url: str, card_raw: str):
    """Shared logic: validate card, run hitter, format response."""
    card = _parse_card(card_raw)
    if not card:
        await update.message.reply_text(
            "❌ Invalid card format. Use: <code>CC|MM|YY|CVV</code>",
            parse_mode=ParseMode.HTML
        )
        return

    msg = await update.message.reply_text(
        f"⏳ Hitting <b>{gateway}</b> checkout…", parse_mode=ParseMode.HTML
    )

    user_id = update.effective_user.id
    t0 = time.time()
    result = {}

    try:
        if gateway == "checkout":
            from modules.freaky.checkout_hitter import CheckoutHitter
            hitter = CheckoutHitter(url)
            result = await hitter.hit(card_raw, 1, user_id)

        elif gateway == "adyen":
            from modules.freaky.adyen_hitter import AdyenHitter
            hitter = AdyenHitter(url)
            result = await hitter.hit(card, 1, user_id)

        elif gateway == "adyen_ccn":
            from modules.freaky.adyen_hitter import AdyenHitter
            hitter = AdyenHitter(url)
            result = await hitter.hit_ccn(card, 1, user_id)

        elif gateway == "epoch":
            from modules.freaky.epoch_hitter import EpochHitter
            hitter = EpochHitter(url)
            result = await hitter.hit(card, 1, user_id)

        elif gateway == "paddle":
            from modules.freaky.paddle_hitter import PaddleHitter
            hitter = PaddleHitter(url)
            result = await hitter.hit(card, 1, user_id)

        elif gateway == "whop":
            from modules.freaky.whop_hitter import WhopHitter
            hitter = WhopHitter(url)
            result = await hitter.hit(card, 1, user_id)

        elif gateway == "mpgs":
            from modules.freaky.mpgs_hitter import MPGSHitter
            result = await MPGSHitter.process_card(url, card)

    except Exception as e:
        result = {"success": False, "error": str(e), "decline_code": "exception"}

    elapsed = time.time() - t0
    text = _format_hit_result(result, gateway, card_raw, elapsed)
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  /hitck — Checkout.com hitter
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_hitck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            _usage("/hitck", "<url> <CC|MM|YY|CVV>",
                   "/hitck https://pay.checkout.com/page/xxx 4111111111111111|12|26|123"),
            parse_mode=ParseMode.HTML
        )
        return
    url, card_raw = context.args[0], context.args[1]
    await _run_hitter(update, context, "checkout", url, card_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  /hitad — Adyen hitter (full 3DS)
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_hitad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            _usage("/hitad", "<url> <CC|MM|YY|CVV>",
                   "/hitad https://pay.adyen.com/... 4111111111111111|12|26|123"),
            parse_mode=ParseMode.HTML
        )
        return
    url, card_raw = context.args[0], context.args[1]
    await _run_hitter(update, context, "adyen", url, card_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  /hitad1 — Adyen CCN-only hitter (no CVV required)
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_hitad1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            _usage("/hitad1", "<url> <CC|MM|YY>",
                   "/hitad1 https://pay.adyen.com/... 4111111111111111|12|26"),
            parse_mode=ParseMode.HTML
        )
        return
    url, card_raw = context.args[0], context.args[1]
    await _run_hitter(update, context, "adyen_ccn", url, card_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  /hitmpgs — MPGS hitter
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_hitmpgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            _usage("/hitmpgs", "<url> <CC|MM|YY|CVV>",
                   "/hitmpgs https://merchant.com/pay/xxx 4111111111111111|12|26|123"),
            parse_mode=ParseMode.HTML
        )
        return
    url, card_raw = context.args[0], context.args[1]
    await _run_hitter(update, context, "mpgs", url, card_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  /hitwhop — Whop hitter
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_hitwhop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            _usage("/hitwhop", "<url> <CC|MM|YY|CVV>",
                   "/hitwhop https://whop.com/checkout/... 4111111111111111|12|26|123"),
            parse_mode=ParseMode.HTML
        )
        return
    url, card_raw = context.args[0], context.args[1]
    await _run_hitter(update, context, "whop", url, card_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  /hitpad — Paddle hitter
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_hitpad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            _usage("/hitpad", "<url> <CC|MM|YY|CVV>",
                   "/hitpad https://buy.paddle.com/... 4111111111111111|12|26|123"),
            parse_mode=ParseMode.HTML
        )
        return
    url, card_raw = context.args[0], context.args[1]
    await _run_hitter(update, context, "paddle", url, card_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  /hitep — Epoch hitter
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_hitep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            _usage("/hitep", "<url> <CC|MM|YY|CVV>",
                   "/hitep https://epoch.com/... 4111111111111111|12|26|123"),
            parse_mode=ParseMode.HTML
        )
        return
    url, card_raw = context.args[0], context.args[1]
    await _run_hitter(update, context, "epoch", url, card_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  /jio — Jio mobile recharge hitter
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_jio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            _usage("/jio", "<mobile> <plan_id> <CC|MM|YY|CVV>",
                   "/jio 9876543210 239 4111111111111111|12|26|123"),
            parse_mode=ParseMode.HTML
        )
        return

    phone = context.args[0].strip()
    plan_id = context.args[1].strip()
    card_raw = context.args[2].strip()

    card = _parse_card(card_raw)
    if not card:
        await update.message.reply_text("❌ Invalid card format.", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text("⏳ Attempting Jio recharge…", parse_mode=ParseMode.HTML)
    t0 = time.time()

    try:
        from modules.freaky.jio_hitter import JioHitter
        hitter = JioHitter(phone, plan_id)
        result = await hitter.hit(card)
    except Exception as e:
        result = {"success": False, "error": str(e), "decline_code": "exception"}

    elapsed = time.time() - t0
    text = _format_hit_result(result, "JIO", card_raw, elapsed)
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  /iban — Generate IBAN(s)
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_iban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            _usage("/iban", "<country_code> [count]",
                   "/iban DE 5\n/iban US\n/iban GB 10"),
            parse_mode=ParseMode.HTML
        )
        return

    country = context.args[0].upper()
    count = 1
    if len(context.args) > 1:
        try:
            count = max(1, min(int(context.args[1]), 50))
        except ValueError:
            pass

    try:
        from modules.freaky_generators import generate_iban
        ibans = [generate_iban(country) for _ in range(count)]
        sep = "━━━━━━━━━━━━━━━━━━━━"
        lines = "\n".join(f"<code>{ib}</code>" for ib in ibans if ib)
        if not lines:
            await update.message.reply_text(f"❌ Unsupported country: <code>{country}</code>", parse_mode=ParseMode.HTML)
            return
        text = f"💜 <b>ONICHAN • IBAN GENERATOR</b>\n{sep}\n🌍 <b>Country</b>: {country}\n{sep}\n{lines}"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  /ibancountry — List supported IBAN countries
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_ibancountry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from modules.freaky_generators import IBAN_COUNTRIES
        sep = "━━━━━━━━━━━━━━━━━━━━"
        lines = []
        for code, info in sorted(IBAN_COUNTRIES.items()):
            flag = info.get("flag", "")
            name = info.get("name", code)
            lines.append(f"{flag} <code>{code}</code> — {name}")
        text = f"💜 <b>ONICHAN • IBAN COUNTRIES</b>\n{sep}\n" + "\n".join(lines)
        # Split if too long
        if len(text) > 4000:
            text = text[:3990] + "\n…"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  /pick — Pick N random lines from a card list
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            _usage("/pick", "<count>",
                   "/pick 10\n(reply to or attach a .txt file of cards)"),
            parse_mode=ParseMode.HTML
        )
        return

    try:
        count = max(1, min(int(context.args[0]), 10000))
    except ValueError:
        await update.message.reply_text("❌ Count must be a number.", parse_mode=ParseMode.HTML)
        return

    # Get source text — from replied-to message or document caption doc
    text = None
    if update.message.reply_to_message:
        msg_r = update.message.reply_to_message
        if msg_r.document and (msg_r.document.file_name or "").endswith(".txt"):
            tg_file = await context.bot.get_file(msg_r.document.file_id)
            raw = await tg_file.download_as_bytearray()
            text = bytes(raw).decode("utf-8", errors="ignore")
        elif msg_r.text:
            text = msg_r.text

    if not text:
        await update.message.reply_text(
            "📎 Reply to a message or .txt file containing the card list.",
            parse_mode=ParseMode.HTML
        )
        return

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        await update.message.reply_text("❌ No lines found.", parse_mode=ParseMode.HTML)
        return

    picked = random.sample(lines, min(count, len(lines)))
    result_text = "\n".join(picked)
    sep = "━━━━━━━━━━━━━━━━━━━━"
    header = f"💜 <b>ONICHAN • PICK</b>\n{sep}\n📊 <b>Picked</b>: {len(picked)}/{len(lines)}\n{sep}\n"

    if len(picked) <= 20:
        out = header + "\n".join(f"<code>{l}</code>" for l in picked)
        await update.message.reply_text(out, parse_mode=ParseMode.HTML)
    else:
        buf = io.BytesIO(result_text.encode())
        buf.name = f"picked_{len(picked)}.txt"
        await update.message.reply_text(header + f"<i>{len(picked)} cards picked — sending as file.</i>", parse_mode=ParseMode.HTML)
        await update.message.reply_document(document=buf, filename=f"picked_{len(picked)}.txt")


# ══════════════════════════════════════════════════════════════════════════════
#  /split — Split card list into chunks
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            _usage("/split", "<lines_per_file>",
                   "/split 100\n(reply to a .txt file of cards)"),
            parse_mode=ParseMode.HTML
        )
        return

    try:
        per = max(1, int(context.args[0]))
    except ValueError:
        await update.message.reply_text("❌ Must be a number.", parse_mode=ParseMode.HTML)
        return

    text = None
    if update.message.reply_to_message:
        msg_r = update.message.reply_to_message
        if msg_r.document and (msg_r.document.file_name or "").endswith(".txt"):
            tg_file = await context.bot.get_file(msg_r.document.file_id)
            raw = await tg_file.download_as_bytearray()
            text = bytes(raw).decode("utf-8", errors="ignore")
        elif msg_r.text:
            text = msg_r.text

    if not text:
        await update.message.reply_text("📎 Reply to a message or .txt file.", parse_mode=ParseMode.HTML)
        return

    from modules.freaky_file_tools import split_text_lines_per_file
    chunks = split_text_lines_per_file(text, per)
    if not chunks:
        await update.message.reply_text("❌ No content to split.", parse_mode=ParseMode.HTML)
        return

    sep = "━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(
        f"💜 <b>ONICHAN • SPLIT</b>\n{sep}\n📦 Sending <b>{len(chunks)}</b> files ({per} lines each)…",
        parse_mode=ParseMode.HTML
    )

    for idx, chunk in enumerate(chunks[:20], 1):
        buf = io.BytesIO(chunk.encode())
        buf.name = f"part_{idx:02d}.txt"
        await update.message.reply_document(document=buf, filename=f"part_{idx:02d}.txt")

    if len(chunks) > 20:
        await update.message.reply_text(
            f"⚠️ Only sent first 20 of {len(chunks)} parts to avoid spam.",
            parse_mode=ParseMode.HTML
        )


# ══════════════════════════════════════════════════════════════════════════════
#  /country — Group cards by BIN country
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = None
    if update.message.reply_to_message:
        msg_r = update.message.reply_to_message
        if msg_r.document and (msg_r.document.file_name or "").endswith(".txt"):
            tg_file = await context.bot.get_file(msg_r.document.file_id)
            raw = await tg_file.download_as_bytearray()
            text = bytes(raw).decode("utf-8", errors="ignore")
        elif msg_r.text:
            text = msg_r.text

    if not text:
        await update.message.reply_text(
            "📎 Reply to a card list (.txt or message) with <code>/country</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    msg = await update.message.reply_text("⏳ Looking up BINs and grouping by country…", parse_mode=ParseMode.HTML)

    try:
        from modules.freaky_file_tools import group_text_by_country
        groups, meta = await group_text_by_country(text)

        if not groups:
            await msg.edit_text("❌ No valid cards found.", parse_mode=ParseMode.HTML)
            return

        sep = "━━━━━━━━━━━━━━━━━━━━"
        summary_lines = []
        for country, cards in sorted(groups.items(), key=lambda x: -len(x[1])):
            m = meta.get(country, {})
            flag = m.get("flag", "🌐")
            summary_lines.append(f"{flag} <b>{country}</b>: {len(cards)} cards")

        header = f"💜 <b>ONICHAN • COUNTRY GROUP</b>\n{sep}\n" + "\n".join(summary_lines) + f"\n{sep}"
        await msg.edit_text(header, parse_mode=ParseMode.HTML)

        # Send a file per country
        for country, cards in sorted(groups.items(), key=lambda x: -len(x[1])):
            m = meta.get(country, {})
            flag = m.get("flag", "🌐")
            code = m.get("code", "UNK")
            buf = io.BytesIO("\n".join(cards).encode())
            fname = f"{code}_{len(cards)}.txt"
            caption = f"{flag} <b>{country}</b> — {len(cards)} cards"
            await update.message.reply_document(document=buf, filename=fname, caption=caption, parse_mode=ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}", parse_mode=ParseMode.HTML)
