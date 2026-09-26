"""
FreakyHitter Telegram command handlers for Onichan Bot.
Rewritten to use the FreakyHitter-main gateway engines directly.
"""
import re
import io
import random
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode


# ─── Card / proxy parsing ─────────────────────────────────────────────────────

def _parse_card_str(card_str: str) -> Optional[dict]:
    """Parse 'cc|mm|yy|cvv' into a card dict expected by the gateway engines."""
    parts = re.split(r'[|/:\s]', card_str.strip())
    if len(parts) < 4:
        return None
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if not cc.isdigit() or len(cc) < 13:
        return None
    if len(yy) == 4:
        yy = yy[2:]
    return {"card": cc, "month": mm.zfill(2), "year": yy, "cvv": cvv}


def _parse_proxy_str(proxy_str: Optional[str]) -> Optional[dict]:
    """Convert a proxy URL string into the dict the gateway engines expect."""
    if not proxy_str or not proxy_str.startswith(
        ("http://", "https://", "socks4://", "socks5://")
    ):
        return None
    try:
        from urllib.parse import urlparse
        p = urlparse(proxy_str)
        d: dict = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
        if p.username:
            d["username"] = p.username
        if p.password:
            d["password"] = p.password
        return d
    except Exception:
        return None


# ─── Hitter arg parsing ───────────────────────────────────────────────────────

def _parse_hitter_args(args):
    """Parse [url, card, proxy?] from a Telegram args list."""
    text = " ".join(args).strip()
    parts = text.split()
    url = card = proxy = None

    for i, part in enumerate(parts):
        if part.startswith("http://") or part.startswith("https://"):
            url = part
            remaining = parts[i + 1 :]
            for j, r in enumerate(remaining):
                if "|" in r or re.match(r"^\d{13,19}", r):
                    card = r
                    rest = remaining[j + 1 :]
                    if rest and rest[0].startswith(("http://", "https://", "socks")):
                        proxy = rest[0]
                    break
            break

    if not url and len(parts) >= 2:
        url = parts[0]
        card = parts[1]
        if len(parts) >= 3 and parts[2].startswith(
            ("http://", "https://", "socks4://", "socks5://")
        ):
            proxy = parts[2]

    return url, card, proxy


# ─── Result normaliser ────────────────────────────────────────────────────────

def _normalize_result(result: dict, gateway: str) -> dict:
    """
    Convert any FreakyHitter gateway result dict into the
    {status, message, gateway, time_taken} format used by _format_hit_result.
    """
    t = result.get("response_time") or result.get("time_taken", 0)

    # JioHitter-style status codes
    jio_status = result.get("status", "")
    if jio_status == "APPROVED@PAID":
        return {"status": "live", "message": "Recharge Successful ✅", "gateway": gateway, "time_taken": t}
    if jio_status == "3DS_CHALLENGE":
        return {"status": "3ds", "message": str(result.get("error") or "OTP/3DS Required"), "gateway": gateway, "time_taken": t}
    if jio_status == "DECLINED":
        return {"status": "decline", "message": str(result.get("error") or "Payment Declined") + " ❌", "gateway": gateway, "time_taken": t}
    if jio_status == "ERROR":
        return {"status": "error", "message": str(result.get("error") or "Error"), "gateway": gateway, "time_taken": t}

    # Standard success / decline / error pattern
    if result.get("success"):
        return {"status": "live", "message": "Payment Approved ✅", "gateway": gateway, "time_taken": t}

    dc = str(result.get("decline_code") or "")
    err = str(result.get("error") or "Declined")

    if "3ds" in dc.lower() or dc in ("3ds_required", "3ds_challenge"):
        return {"status": "3ds", "message": err or "OTP/3DS Required 🔐", "gateway": gateway, "time_taken": t}

    if result.get("is_live") or dc in ("insufficient_funds", "incorrect_cvc", "restricted_card"):
        return {"status": "live", "message": err + " 💳", "gateway": gateway, "time_taken": t}

    if dc == "exception":
        return {"status": "error", "message": err, "gateway": gateway, "time_taken": t}

    return {"status": "decline", "message": err + " ❌", "gateway": gateway, "time_taken": t}


def _format_hit_result(result: dict, card: str) -> str:
    status = result.get("status", "error")
    message = result.get("message", "Unknown")
    gateway = result.get("gateway", "Unknown")
    time_taken = result.get("time_taken", 0)

    if status == "live":
        emoji, header = "✅", "APPROVED"
    elif status == "3ds":
        emoji, header = "🔐", "3DS REQUIRED"
    elif status == "decline":
        emoji, header = "❌", "DECLINED"
    else:
        emoji, header = "⚠️", "ERROR"

    sep = "━━━━━━━━━━━━━━━━━━━━"
    return (
        f"{emoji} <b>ONICHAN • {header}</b>\n\n"
        f"{sep}\n"
        f"💳 <b>Card</b>    : <code>{card}</code>\n"
        f"🌐 <b>Gateway</b> : {gateway}\n"
        f"📋 <b>Result</b>  : {message}\n"
        f"⏱ <b>Time</b>    : {time_taken}s\n"
        f"{sep}"
    )


# ─── Gateway adapter coroutines ───────────────────────────────────────────────

async def _hit_checkout(url: str, card_str: str, proxy_str: Optional[str]) -> dict:
    from modules.freaky.checkout_hitter import CheckoutHitter
    card = _parse_card_str(card_str)
    if not card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Checkout.com", "time_taken": 0}
    proxy_data = _parse_proxy_str(proxy_str)
    hitter = CheckoutHitter(url=url, proxy_data=proxy_data)
    result = await hitter.hit(card, index=1, user_id=0)
    return _normalize_result(result, "Checkout.com")


async def _hit_adyen(url: str, card_str: str, proxy_str: Optional[str]) -> dict:
    from modules.freaky.adyen_hitter import AdyenHitter
    card = _parse_card_str(card_str)
    if not card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Adyen", "time_taken": 0}
    proxy_data = _parse_proxy_str(proxy_str)
    hitter = AdyenHitter(url=url, proxy_data=proxy_data)
    result = await hitter.hit(card, attempt=1, user_id=0)
    return _normalize_result(result, "Adyen")


async def _hit_mpgs(url: str, card_str: str, proxy_str: Optional[str]) -> dict:
    from modules.freaky.mpgs_hitter import MPGSHitter
    card = _parse_card_str(card_str)
    if not card:
        return {"status": "error", "message": "Invalid card format", "gateway": "MPGS", "time_taken": 0}
    proxy_data = _parse_proxy_str(proxy_str)
    result = await MPGSHitter.process_card(url, card, proxy_data)
    return _normalize_result(result, "MPGS")


async def _hit_whop(url: str, card_str: str, proxy_str: Optional[str]) -> dict:
    from modules.freaky.whop_hitter import WhopHitter
    card = _parse_card_str(card_str)
    if not card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Whop", "time_taken": 0}
    proxy_data = _parse_proxy_str(proxy_str)
    hitter = WhopHitter(url=url, proxy_data=proxy_data)
    result = await hitter.hit(card, attempt=1, user_id=0)
    return _normalize_result(result, "Whop")


async def _hit_paddle(url: str, card_str: str, proxy_str: Optional[str]) -> dict:
    from modules.freaky.paddle_hitter import PaddleHitter
    card = _parse_card_str(card_str)
    if not card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Paddle", "time_taken": 0}
    proxy_data = _parse_proxy_str(proxy_str)
    hitter = PaddleHitter(url=url, proxy_data=proxy_data)
    result = await hitter.hit(card, attempt=1, user_id=0)
    return _normalize_result(result, "Paddle")


async def _hit_epoch(url: str, card_str: str, proxy_str: Optional[str]) -> dict:
    from modules.freaky.epoch_hitter import EpochHitter
    card = _parse_card_str(card_str)
    if not card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Epoch", "time_taken": 0}
    proxy_data = _parse_proxy_str(proxy_str)
    hitter = EpochHitter(url=url, proxy_data=proxy_data)
    result = await hitter.hit(card, attempt=1, user_id=0)
    return _normalize_result(result, "Epoch")


# ─── Generic handler factory ──────────────────────────────────────────────────

def _make_hitter_handler(hitter_coro, gateway_name: str):
    """Build a Telegram command handler around a hitter coroutine."""
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                f"💜 <b>ONICHAN • {gateway_name.upper()} HITTER</b>\n\n"
                f"📝 <b>Usage</b>: <code>/{gateway_name.lower()} &lt;url&gt; &lt;card|mm|yy|cvv&gt;</code>\n\n"
                f"📌 <b>Example</b>:\n"
                f"<code>/{gateway_name.lower()} https://example.com/checkout 4242424242424242|12|28|123</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        url, card, proxy = _parse_hitter_args(context.args)
        if not url or not card:
            await update.message.reply_text(
                f"❌ Usage: <code>/{gateway_name.lower()} &lt;url&gt; &lt;card|mm|yy|cvv&gt;</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        loading_msg = await update.message.reply_text(
            f"⌛️ <b>Hitting {gateway_name}...</b>\n💳 <code>{card}</code>",
            parse_mode=ParseMode.HTML,
        )
        try:
            result = await hitter_coro(url, card, proxy)
            await loading_msg.edit_text(
                _format_hit_result(result, card), parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await loading_msg.edit_text(
                f"⚠️ <b>Error:</b> {str(e)[:200]}", parse_mode=ParseMode.HTML
            )

    return handler


# ─── Individual command handlers ──────────────────────────────────────────────

async def cmd_hitck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _make_hitter_handler(_hit_checkout, "Checkout.com")(update, context)

async def cmd_hitad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _make_hitter_handler(_hit_adyen, "Adyen")(update, context)

async def cmd_hitad1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _make_hitter_handler(_hit_adyen, "Adyen v2")(update, context)

async def cmd_hitmpgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _make_hitter_handler(_hit_mpgs, "MPGS")(update, context)

async def cmd_hitwhop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _make_hitter_handler(_hit_whop, "Whop")(update, context)

async def cmd_hitpad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _make_hitter_handler(_hit_paddle, "Paddle")(update, context)

async def cmd_hitep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _make_hitter_handler(_hit_epoch, "Epoch")(update, context)


async def cmd_hitjio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit Jio recharge using JioHitter (the full PayGlocal/JioPG flow)."""
    if not context.args:
        await update.message.reply_text(
            "💜 <b>ONICHAN • JIO HITTER</b>\n\n"
            "📝 <b>Usage</b>: <code>/jio &lt;mobile&gt; &lt;card|mm|yy|cvv&gt;</code>\n\n"
            "📌 <b>Examples</b>:\n"
            "<code>/jio 9876543210 4532111111111111|12|28|123</code>\n"
            "<code>/jio https://jio.com/pay 4532111111111111|12|28|123</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Usage: <code>/jio &lt;mobile&gt; &lt;card|mm|yy|cvv&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target = context.args[0]
    card_str = context.args[1]
    # arg[2] is only treated as proxy if it looks like a valid proxy URL
    raw_proxy = context.args[2] if len(context.args) > 2 else None
    proxy_str = (
        raw_proxy
        if raw_proxy and raw_proxy.startswith(("http://", "https://", "socks4://", "socks5://"))
        else None
    )

    card = _parse_card_str(card_str)
    if not card:
        await update.message.reply_text("❌ Invalid card format.", parse_mode=ParseMode.HTML)
        return

    loading_msg = await update.message.reply_text(
        f"⌛️ <b>Hitting Jio...</b>\n💳 <code>{card_str}</code>",
        parse_mode=ParseMode.HTML,
    )
    try:
        from modules.freaky.jio_hitter import JioHitter
        proxy_data = _parse_proxy_str(proxy_str)
        hitter = JioHitter(phone_number=target, proxy_data=proxy_data)
        result = await hitter.hit(card)
        normalized = _normalize_result(result, "Jio")
        await loading_msg.edit_text(
            _format_hit_result(normalized, card_str), parse_mode=ParseMode.HTML
        )
    except Exception as e:
        err = str(e).strip()
        if not err or len(err) <= 8 or err.replace(".", "").isdigit():
            err = f"Connection failed ({err})" if err else "Connection failed"
        await loading_msg.edit_text(
            f"⚠️ <b>Error:</b> {err[:200]}", parse_mode=ParseMode.HTML
        )


# ─── IBAN generator ───────────────────────────────────────────────────────────

async def cmd_iban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from modules.freaky_generators import generate_valid_iban, IBAN_COUNTRIES

    country_arg = " ".join(context.args).strip().upper() if context.args else "DE"

    # Try exact 2-letter code first, then name fuzzy match
    country_code = None
    if country_arg in IBAN_COUNTRIES:
        country_code = country_arg
    else:
        for code, info in IBAN_COUNTRIES.items():
            if country_arg.lower() in info.get("name", "").lower():
                country_code = code
                break
    if not country_code:
        country_code = "DE"

    try:
        info = generate_valid_iban(country_code)
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = (
            f"🏦 <b>ONICHAN • IBAN GENERATOR</b>\n\n"
            f"{sep}\n"
            f"{info['flag']} <b>Country</b>  : {info['country']}\n"
            f"💳 <b>IBAN</b>     : <code>{info['iban']}</code>\n"
            f"🏛 <b>Bank</b>     : {info['bank_name']}\n"
            f"🔢 <b>BIC</b>      : <code>{info.get('bic', 'N/A')}</code>\n"
            f"💼 <b>Account</b>  : <code>{info.get('account_no', 'N/A')}</code>\n"
            f"{sep}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)[:200]}", parse_mode=ParseMode.HTML)


async def cmd_ibancountry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from modules.freaky_generators import IBAN_COUNTRIES

    sep = "━━━━━━━━━━━━━━━━━━━━"
    lines = [
        f"{info.get('flag', '🌍')} <code>{code}</code> — {info.get('name', code)}"
        for code, info in list(IBAN_COUNTRIES.items())[:50]
    ]
    text = (
        f"🌍 <b>ONICHAN • IBAN COUNTRIES</b>\n\n"
        f"{sep}\n"
        + "\n".join(lines)
        + f"\n{sep}\n"
        f"Usage: <code>/iban DE</code> or <code>/iban Germany</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ─── File tool commands ───────────────────────────────────────────────────────

async def cmd_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pick N random cards from an attached .txt file."""
    n = None
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            pass

    if not n or n <= 0:
        await update.message.reply_text(
            "🎲 <b>ONICHAN • CARD PICKER</b>\n\n"
            "Usage: <code>/pick &lt;n&gt;</code> — attach a .txt or reply to one.\n"
            "Example: <code>/pick 10</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    if n > 1000:
        await update.message.reply_text("❌ Maximum 1000 cards per pick.", parse_mode=ParseMode.HTML)
        return

    msg = update.message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document
    if not doc or not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "📎 Please attach a <b>.txt</b> file (or reply to one).",
            parse_mode=ParseMode.HTML,
        )
        return

    loading = await update.message.reply_text("🎲 Picking cards...", parse_mode=ParseMode.HTML)
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        text_content = bytes(file_bytes).decode("utf-8", errors="ignore")

        lines = [l.strip() for l in text_content.splitlines() if l.strip()]
        if not lines:
            await loading.edit_text("❌ No cards found in file.")
            return

        picked = random.sample(lines, min(n, len(lines)))
        output_text = "\n".join(picked)

        sep = "━━━━━━━━━━━━━━━━━━━━"
        summary = (
            f"🎲 <b>CARD PICKER</b>\n\n"
            f"{sep}\n"
            f"📊 <b>Total</b>  : {len(lines)}\n"
            f"🎯 <b>Picked</b> : {len(picked)}\n"
            f"{sep}"
        )
        await loading.delete()
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)
        file_obj = io.BytesIO(output_text.encode("utf-8"))
        await update.message.reply_document(
            document=file_obj,
            filename=f"picked_{len(picked)}cards.txt",
            caption=f"🎲 {len(picked)} randomly picked cards",
        )
    except Exception as e:
        await loading.edit_text(f"⚠️ Error: {str(e)[:200]}")


async def cmd_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Split a .txt file of cards into N equal parts."""
    n = None
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            pass

    if not n or n <= 0:
        await update.message.reply_text(
            "✂️ <b>ONICHAN • CARD SPLITTER</b>\n\n"
            "Usage: <code>/split &lt;n&gt;</code> — attach a .txt or reply to one.\n"
            "Example: <code>/split 4</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    if n > 100:
        await update.message.reply_text("❌ Maximum 100 splits.", parse_mode=ParseMode.HTML)
        return

    msg = update.message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document
    if not doc or not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "📎 Please attach a <b>.txt</b> file (or reply to one).",
            parse_mode=ParseMode.HTML,
        )
        return

    loading = await update.message.reply_text("✂️ Splitting cards...", parse_mode=ParseMode.HTML)
    try:
        from modules.freaky_file_tools import split_text_n_parts

        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        text_content = bytes(file_bytes).decode("utf-8", errors="ignore")

        chunks = split_text_n_parts(text_content, n)
        if not chunks:
            await loading.edit_text("❌ No cards found in file.")
            return

        total_lines = sum(len([l for l in c.splitlines() if l.strip()]) for c in chunks)
        sep = "━━━━━━━━━━━━━━━━━━━━"
        summary = (
            f"✂️ <b>CARD SPLITTER</b>\n\n"
            f"{sep}\n"
            f"📊 <b>Total</b>     : {total_lines}\n"
            f"📦 <b>Parts</b>     : {len(chunks)}\n"
            f"🎯 <b>~Per part</b> : {total_lines // max(len(chunks), 1)}\n"
            f"{sep}"
        )
        await loading.delete()
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)
        for i, chunk in enumerate(chunks, 1):
            count = len([l for l in chunk.splitlines() if l.strip()])
            file_obj = io.BytesIO(chunk.encode("utf-8"))
            await update.message.reply_document(
                document=file_obj,
                filename=f"part_{i}_{count}cards.txt",
                caption=f"📦 Part {i}/{len(chunks)} — {count} cards",
            )
    except Exception as e:
        await loading.edit_text(f"⚠️ Error: {str(e)[:200]}")


async def cmd_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show country distribution of cards in an attached .txt file."""
    msg = update.message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document
    if not doc or not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "🌍 <b>ONICHAN • COUNTRY ANALYZER</b>\n\n"
            "Attach a .txt file and use <code>/country</code> as caption,\n"
            "or reply to an existing .txt file with <code>/country</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    loading = await update.message.reply_text(
        "🌍 Analyzing countries...", parse_mode=ParseMode.HTML
    )
    try:
        from modules.freaky_file_tools import group_text_by_country

        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        text_content = bytes(file_bytes).decode("utf-8", errors="ignore")

        country_groups, country_meta = await group_text_by_country(text_content)
        total = sum(len(v) for v in country_groups.values())
        sorted_countries = sorted(country_groups.items(), key=lambda x: -len(x[1]))

        sep = "━━━━━━━━━━━━━━━━━━━━"
        lines = [
            f"{country_meta.get(c, {}).get('flag', '🌐')} <b>{c}</b>: {len(cards)}"
            for c, cards in sorted_countries[:30]
        ]
        text = (
            f"🌍 <b>ONICHAN • COUNTRY STATS</b>\n\n"
            f"{sep}\n"
            f"📊 <b>Total cards</b> : {total}\n"
            f"🌐 <b>Countries</b>   : {len(country_groups)}\n\n"
            + "\n".join(lines)
            + f"\n{sep}"
        )
        await loading.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await loading.edit_text(f"⚠️ Error: {str(e)[:200]}")
