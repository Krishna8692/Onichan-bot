"""
FreakyHitter Telegram command handlers for Onichan Bot.
All new /hit* commands, /jio, /iban, /ibancountry, /pick, /split, /country.
Import this file in bot.py and register the handlers.
"""
import re
import time
import asyncio
import io
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode


def _run_freaky_async(coro):
    """Run a freaky hitter coroutine synchronously in a new event loop."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _parse_hitter_args(args):
    """Parse 'url card' or 'url card proxy' from command args."""
    text = ' '.join(args).strip()
    parts = text.split()
    url = None
    card = None
    proxy = None

    for i, part in enumerate(parts):
        if part.startswith('http://') or part.startswith('https://'):
            url = part
            remaining = parts[i+1:]
            # Card is next pipe-separated group
            for j, r in enumerate(remaining):
                if '|' in r or re.match(r'^\d{13,19}', r):
                    card = r
                    proxy_parts = remaining[j+1:]
                    if proxy_parts:
                        proxy = proxy_parts[0]
                    break
            break

    if not url:
        # Maybe URL first then card
        if len(parts) >= 2:
            url = parts[0]
            card = parts[1]
            if len(parts) >= 3:
                proxy = parts[2]

    return url, card, proxy


def _format_hit_result(result: dict, card: str) -> str:
    status = result.get('status', 'error')
    message = result.get('message', 'Unknown')
    gateway = result.get('gateway', 'Unknown')
    time_taken = result.get('time_taken', 0)

    if status == 'live':
        emoji = '✅'
        header = 'APPROVED'
    elif status == '3ds':
        emoji = '🔐'
        header = '3DS REQUIRED'
    elif status == 'decline':
        emoji = '❌'
        header = 'DECLINED'
    else:
        emoji = '⚠️'
        header = 'ERROR'

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


# ─── Generic hitter factory ───────────────────────────────────────────────────

def _make_hitter_handler(hitter_func, gateway_name: str, require_prem=True):
    """Create a Telegram command handler for a hitter function."""
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user

        if not context.args:
            await update.message.reply_text(
                f"💜 <b>ONICHAN • {gateway_name.upper()} HITTER</b>\n\n"
                f"📝 <b>Usage</b>: <code>/{gateway_name.lower()} &lt;url&gt; &lt;card|mm|yy|cvv&gt;</code>\n\n"
                f"📌 <b>Example</b>:\n"
                f"<code>/{gateway_name.lower()} https://example.com/checkout 4242424242424242|12|28|123</code>",
                parse_mode=ParseMode.HTML
            )
            return

        url, card, proxy = _parse_hitter_args(context.args)

        if not url or not card:
            await update.message.reply_text(
                f"❌ <b>Invalid format!</b>\n"
                f"Usage: <code>/{gateway_name.lower()} &lt;url&gt; &lt;card|mm|yy|cvv&gt;</code>",
                parse_mode=ParseMode.HTML
            )
            return

        loading_msg = await update.message.reply_text(
            f"⌛️ <b>Hitting {gateway_name}...</b>\n💳 <code>{card}</code>",
            parse_mode=ParseMode.HTML
        )

        try:
            result = await hitter_func(url, card, proxy)
            text = _format_hit_result(result, card)
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            await loading_msg.edit_text(f"⚠️ <b>Error:</b> {str(e)[:200]}", parse_mode=ParseMode.HTML)

    return handler


# ─── Individual command handlers ──────────────────────────────────────────────

async def cmd_hitck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit a Checkout.com payment page."""
    from modules.freaky.freaky_checkout import hit_checkout
    await _make_hitter_handler(hit_checkout, "Checkout.com")(update, context)


async def cmd_hitad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit an Adyen payment page."""
    from modules.freaky.freaky_adyen import hit_adyen
    await _make_hitter_handler(hit_adyen, "Adyen")(update, context)


async def cmd_hitad1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit an Adyen payment page (v2)."""
    from modules.freaky.freaky_adyen import hit_adyen_v2
    await _make_hitter_handler(hit_adyen_v2, "Adyen-v2")(update, context)


async def cmd_hitmpgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit an MPGS payment page."""
    from modules.freaky.freaky_mpgs import hit_mpgs
    await _make_hitter_handler(hit_mpgs, "MPGS")(update, context)


async def cmd_hitwhop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit a Whop checkout page."""
    from modules.freaky.freaky_whop import hit_whop
    await _make_hitter_handler(hit_whop, "Whop")(update, context)


async def cmd_hitpad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit a Paddle checkout page."""
    from modules.freaky.freaky_paddle import hit_paddle
    await _make_hitter_handler(hit_paddle, "Paddle")(update, context)


async def cmd_hitep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit an Epoch checkout page."""
    from modules.freaky.freaky_epoch import hit_epoch
    await _make_hitter_handler(hit_epoch, "Epoch")(update, context)


async def cmd_hitjio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hit Jio payment / recharge."""
    from modules.freaky.freaky_jio import hit_jio

    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "💜 <b>ONICHAN • JIO HITTER</b>\n\n"
            "📝 <b>Usage</b>: <code>/jio &lt;mobile_or_url&gt; &lt;card|mm|yy|cvv&gt;</code>\n\n"
            "📌 <b>Examples</b>:\n"
            "<code>/jio 9876543210 4532111111111111|12|28|123</code>\n"
            "<code>/jio https://jio.com/pay 4532111111111111|12|28|123</code>",
            parse_mode=ParseMode.HTML
        )
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Usage: <code>/jio &lt;mobile_or_url&gt; &lt;card|mm|yy|cvv&gt;</code>", parse_mode=ParseMode.HTML)
        return

    target = args[0]
    card = args[1]
    proxy = args[2] if len(args) > 2 else None

    loading_msg = await update.message.reply_text(
        f"⌛️ <b>Hitting Jio...</b>\n💳 <code>{card}</code>",
        parse_mode=ParseMode.HTML
    )

    try:
        result = await hit_jio(target, card, proxy)
        text = _format_hit_result(result, card)
        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await loading_msg.edit_text(f"⚠️ <b>Error:</b> {str(e)[:200]}", parse_mode=ParseMode.HTML)


# ─── IBAN generators ──────────────────────────────────────────────────────────

async def cmd_iban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a random IBAN, optionally for a specific country."""
    from modules.freaky_generators import generate_iban, resolve_country_code

    country_arg = ' '.join(context.args).strip() if context.args else None
    country_code = None

    if country_arg:
        country_code = resolve_country_code(country_arg)
        if not country_code:
            # Try direct 2-letter code
            country_code = country_arg.upper() if len(country_arg) == 2 else None

    try:
        iban, meta = generate_iban(country_code)
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = (
            f"🏦 <b>ONICHAN • IBAN GENERATOR</b>\n\n"
            f"{sep}\n"
            f"🌍 <b>Country</b> : {meta['flag']} {meta['country']}\n"
            f"💳 <b>IBAN</b>    : <code>{iban}</code>\n"
            f"🔑 <b>BIC</b>     : <code>{meta['bic']}</code>\n"
            f"🏦 <b>Bank</b>    : {meta['bank']}\n"
            f"{sep}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error generating IBAN: {str(e)[:100]}", parse_mode=ParseMode.HTML)


async def cmd_ibancountry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all supported IBAN countries."""
    from modules.freaky_generators import get_supported_countries, IBAN_FORMATS

    countries = sorted(IBAN_FORMATS.items(), key=lambda x: x[1]['country'])
    lines = [f"{info.get('flag', '🏳️')} <code>{code}</code> — {info['country']}" for code, info in countries]

    sep = "━━━━━━━━━━━━━━━━━━━━"
    header = f"🌍 <b>ONICHAN • IBAN COUNTRIES</b> ({len(countries)} countries)\n\n{sep}\n\n"

    # Send in chunks if too long
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > 3800:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


# ─── File tools ───────────────────────────────────────────────────────────────

async def cmd_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pick N random cards from an attached .txt file."""
    from modules.freaky_file_tools import pick_random_cards, parse_cards_from_text, format_cards_as_text

    if not context.args:
        await update.message.reply_text(
            "💜 <b>ONICHAN • CARD PICKER</b>\n\n"
            "📝 Attach a .txt file and use:\n"
            "<code>/pick &lt;count&gt;</code> as the caption\n\n"
            "📌 <b>Example</b>: <code>/pick 50</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        n = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid number.", parse_mode=ParseMode.HTML)
        return

    if n <= 0 or n > 50000:
        await update.message.reply_text("❌ Count must be between 1 and 50,000.", parse_mode=ParseMode.HTML)
        return

    # Check for attached document
    msg = update.message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document

    if not doc or not (doc.file_name or '').endswith('.txt'):
        await update.message.reply_text("📎 Please attach a <b>.txt</b> file (or reply to one).", parse_mode=ParseMode.HTML)
        return

    loading = await update.message.reply_text("🎲 Picking random cards...", parse_mode=ParseMode.HTML)

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        text_content = bytes(file_bytes).decode('utf-8', errors='ignore')

        cards = parse_cards_from_text(text_content)
        if not cards:
            await loading.edit_text("❌ No valid cards found in file.")
            return

        picked = pick_random_cards(cards, n)
        output_text = format_cards_as_text(picked)

        sep = "━━━━━━━━━━━━━━━━━━━━"
        summary = (
            f"🎲 <b>CARD PICKER</b>\n\n"
            f"{sep}\n"
            f"📊 <b>Total in file</b> : {len(cards)}\n"
            f"🎯 <b>Picked</b>       : {len(picked)}\n"
            f"{sep}"
        )

        await loading.delete()
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

        # Send as file if more than 10 cards
        if len(picked) > 10:
            file_obj = io.BytesIO(output_text.encode('utf-8'))
            file_obj.name = f"picked_{len(picked)}.txt"
            await update.message.reply_document(document=file_obj, filename=f"picked_{len(picked)}.txt")
        else:
            await update.message.reply_text(f"<code>{output_text}</code>", parse_mode=ParseMode.HTML)

    except Exception as e:
        await loading.edit_text(f"⚠️ Error: {str(e)[:200]}")


async def cmd_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Split cards from a .txt file into N parts."""
    from modules.freaky_file_tools import split_cards, parse_cards_from_text, format_cards_as_text

    if not context.args:
        await update.message.reply_text(
            "💜 <b>ONICHAN • CARD SPLITTER</b>\n\n"
            "📝 Attach a .txt file and use:\n"
            "<code>/split &lt;count&gt;</code> as the caption\n\n"
            "📌 <b>Example</b>: <code>/split 5</code> → splits into 5 equal parts",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        n = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid number.", parse_mode=ParseMode.HTML)
        return

    if n <= 0 or n > 100:
        await update.message.reply_text("❌ Split count must be between 1 and 100.", parse_mode=ParseMode.HTML)
        return

    msg = update.message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document

    if not doc or not (doc.file_name or '').endswith('.txt'):
        await update.message.reply_text("📎 Please attach a <b>.txt</b> file (or reply to one).", parse_mode=ParseMode.HTML)
        return

    loading = await update.message.reply_text("✂️ Splitting cards...", parse_mode=ParseMode.HTML)

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        text_content = bytes(file_bytes).decode('utf-8', errors='ignore')

        cards = parse_cards_from_text(text_content)
        if not cards:
            await loading.edit_text("❌ No valid cards found in file.")
            return

        chunks = split_cards(cards, n)

        sep = "━━━━━━━━━━━━━━━━━━━━"
        summary = (
            f"✂️ <b>CARD SPLITTER</b>\n\n"
            f"{sep}\n"
            f"📊 <b>Total cards</b> : {len(cards)}\n"
            f"📦 <b>Split into</b>  : {len(chunks)} parts\n"
            f"🎯 <b>~Per part</b>   : {len(cards) // max(len(chunks), 1)}\n"
            f"{sep}"
        )

        await loading.delete()
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

        for i, chunk in enumerate(chunks, 1):
            output_text = format_cards_as_text(chunk)
            file_obj = io.BytesIO(output_text.encode('utf-8'))
            file_name = f"part_{i}_{len(chunk)}cards.txt"
            await update.message.reply_document(
                document=file_obj,
                filename=file_name,
                caption=f"📦 Part {i}/{len(chunks)} — {len(chunk)} cards"
            )

    except Exception as e:
        await loading.edit_text(f"⚠️ Error: {str(e)[:200]}")


async def cmd_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show country distribution of cards in an attached .txt file."""
    from modules.freaky_file_tools import parse_cards_from_text, get_country_stats

    msg = update.message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document

    if not doc or not (doc.file_name or '').endswith('.txt'):
        await update.message.reply_text(
            "💜 <b>ONICHAN • COUNTRY ANALYZER</b>\n\n"
            "📝 Attach a .txt file and use <code>/country</code> as the caption,\n"
            "or reply to an existing .txt file with <code>/country</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    loading = await update.message.reply_text("🌍 Analyzing countries...", parse_mode=ParseMode.HTML)

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        text_content = bytes(file_bytes).decode('utf-8', errors='ignore')

        cards = parse_cards_from_text(text_content)
        if not cards:
            await loading.edit_text("❌ No valid cards found in file.")
            return

        stats = get_country_stats(cards)

        sep = "━━━━━━━━━━━━━━━━━━━━"
        lines = [f"{country}: <b>{count}</b>" for country, count in list(stats.items())[:30]]
        text = (
            f"🌍 <b>ONICHAN • COUNTRY STATS</b>\n\n"
            f"{sep}\n"
            f"📊 <b>Total cards</b>: {len(cards)}\n"
            f"🌐 <b>Countries</b>  : {len(stats)}\n\n"
            + "\n".join(lines) +
            f"\n{sep}"
        )

        await loading.edit_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        await loading.edit_text(f"⚠️ Error: {str(e)[:200]}")
