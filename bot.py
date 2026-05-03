"""Mnemos — Telegram bot transport.

A thin wrapper around `oracle.py`. Owns the Telegram UX (BotCommands menu,
onboarding wizard, media-groups, inline buttons, JobQueue for daily horoscopes)
and delegates all real work to the skill module.

Run:
    python bot.py
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from datetime import time as dtime
from pathlib import Path

from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import oracle as oracle_mod
from config import cfg
from memory import Profile, Reading, append_reading, find_reading, recent_readings
from ratelimit import can_mint, check_can_read, commit_read, todays_spend

logging.basicConfig(
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    level=getattr(logging, cfg.log_level.upper(), logging.INFO),
)
log = logging.getLogger("mnemos.bot")

# ----------------------------------------------------------------------
# Brand strings
# ----------------------------------------------------------------------

BRAND = "Mnemos"
TAGLINE = "the oracle that remembers every card it's ever pulled for you"

WELCOME_RETURNING = (
    f"🪞 *Welcome back to {BRAND}.*\n\n"
    "Send a question — anything sitting on your chest — and the cards will answer.\n\n"
    "Tap the menu (☰) for all commands, or type /help."
)

WELCOME_NEW = (
    f"🪞 *{BRAND}* — {TAGLINE}.\n\n"
    "Powered by Hermes Agent (Nous Research) and Kimi K2.6 (Moonshot AI).\n\n"
    "Let's set up your reading profile in 30 seconds. You can change anything later "
    "with /profile."
)

HELP_TEXT = f"""\
🪞 *{BRAND}* — full command guide

*Reading the cards*
  /pull — three-card spread (past · present · future). Add your question after the command, e.g. `/pull will this project ship?`
  /single — one-card reading for a tight question.
  Or just *send a message* with no command — we'll treat it as a question and pull a 3-card spread.

*Astrology*
  /horoscope — today's horoscope for your saved sun sign. `/horoscope leo` overrides the saved sign.

*Your context*
  /profile — view profile (sun sign, birth place, wallet for NFTs).
        `/profile sign aries` · `/profile dob 1995-04-12` · `/profile place "Kyiv, Ukraine"` · `/profile wallet 0x…`
  /history — your last 5 readings.
  /start — re-runs the onboarding wizard if you ever want to redo it.

*Buttons under each reading*
  🔮 *Mint hero card on-chain* — pin the first card's image to IPFS and mint it as an ERC-721 on Base Sepolia. Owner-gated by default.
  📅 *Daily at 9 AM UTC* — register a recurring horoscope at 09:00 UTC.
  🪞 *Pull again* — re-runs the same question with a fresh draw.

*How {BRAND} actually thinks*
  Every reading is appended to a JSONL file scoped to your Telegram ID. The next reading injects up to 30 prior readings into Kimi K2.6's 256K context — so the oracle literally references where you've been.

*Fair use*
  Public users get 3 readings/day and 10 lifetime (anti-abuse — protects the dev's API budget). DM the dev for an invite to lift the cap. Owner is unlimited.

_For reflection, not prescription._
"""

# Top-level slash command menu shown in Telegram's "/" popover.
COMMANDS_MENU = [
    BotCommand("pull", "Pull a 3-card spread (add your question)"),
    BotCommand("single", "Pull one card (add your question)"),
    BotCommand("horoscope", "Today's horoscope for your sun sign"),
    BotCommand("history", "Your last 5 readings"),
    BotCommand("profile", "View / edit your profile"),
    BotCommand("help", "All commands & how Mnemos thinks"),
    BotCommand("start", "Welcome / restart onboarding"),
]

# ----------------------------------------------------------------------
# Static data (zodiac signs, top-10 cities)
# ----------------------------------------------------------------------

ZODIAC_SIGNS: list[tuple[str, str]] = [
    ("♈", "Aries"), ("♉", "Taurus"), ("♊", "Gemini"),
    ("♋", "Cancer"), ("♌", "Leo"), ("♍", "Virgo"),
    ("♎", "Libra"), ("♏", "Scorpio"), ("♐", "Sagittarius"),
    ("♑", "Capricorn"), ("♒", "Aquarius"), ("♓", "Pisces"),
]

TOP_CITIES: list[str] = [
    "New York", "London", "Los Angeles", "Tokyo", "Paris",
    "Berlin", "Dubai", "Singapore", "Mumbai", "São Paulo",
]

# Conversation states for onboarding
(ONB_SIGN, ONB_CITY, ONB_CITY_CUSTOM, ONB_WALLET) = range(4)

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _user_id(update: Update) -> int:
    assert update.effective_user is not None
    return update.effective_user.id


def _user_label(update: Update) -> str:
    u = update.effective_user
    if not u:
        return "anon"
    return f"@{u.username}" if u.username else f"id={u.id}"


def _gate(user_id: int) -> tuple[bool, str | None]:
    """Return (allowed, refusal_message_or_none)."""
    decision = check_can_read(user_id)
    if not decision.allowed:
        return False, decision.user_message
    return True, None


def _is_new_user(user_id: int) -> bool:
    """First-time? Profile exists only if user has interacted before."""
    p = Profile.load(user_id)
    return not (p.sun_sign or p.display_name or p.birth_place)


def _owner_default_wallet() -> str:
    """The deployer wallet derived from DEPLOYER_PRIVATE_KEY. Used as the default
    NFT recipient for the owner so they don't have to set it manually."""
    if not cfg.deployer_private_key:
        return ""
    try:
        from eth_account import Account
        return Account.from_key(cfg.deployer_private_key).address
    except Exception:  # noqa: BLE001
        return ""


def _reading_keyboard(user_id: int, reading_id: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if cfg.is_owner(user_id):
        rows.append([InlineKeyboardButton("🔮 Mint hero card on-chain",
                                          callback_data=f"mint:{reading_id}:0")])
    rows.append([
        InlineKeyboardButton("🪞 Pull again", callback_data="pull_again"),
        InlineKeyboardButton("📅 Daily at 9 AM UTC", callback_data="schedule_daily"),
    ])
    return InlineKeyboardMarkup(rows)


def _signs_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, 12, 3):
        row = [
            InlineKeyboardButton(f"{em} {name}", callback_data=f"onb:sign:{name}")
            for em, name in ZODIAC_SIGNS[i:i + 3]
        ]
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _cities_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, 10, 2):
        row = [
            InlineKeyboardButton(c, callback_data=f"onb:city:{c}")
            for c in TOP_CITIES[i:i + 2]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️  Type my own city", callback_data="onb:city:_custom")])
    return InlineKeyboardMarkup(rows)


def _wallet_keyboard() -> InlineKeyboardMarkup:
    """Owner-only step: pick wallet for NFT recipients."""
    rows: list[list[InlineKeyboardButton]] = []
    default = _owner_default_wallet()
    if default:
        rows.append([InlineKeyboardButton(
            f"🤖 Use server wallet ({default[:6]}…{default[-4:]})",
            callback_data="onb:wallet:_default")])
    rows.append([InlineKeyboardButton("✏️  Paste my own wallet (0x…)",
                                      callback_data="onb:wallet:_custom")])
    rows.append([InlineKeyboardButton("⏭  Skip for now", callback_data="onb:wallet:_skip")])
    return InlineKeyboardMarkup(rows)


# ----------------------------------------------------------------------
# Onboarding wizard (ConversationHandler)
# ----------------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = _user_id(update)
    log.info("/start from %s (new=%s)", _user_label(update), _is_new_user(user_id))

    if not _is_new_user(user_id):
        # Returning user — short welcome, end any active conversation
        await update.message.reply_text(WELCOME_RETURNING, parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    # Initialise profile with display_name from Telegram so we know they've started
    profile = Profile.load(user_id)
    profile.display_name = update.effective_user.full_name or f"user-{user_id}"
    profile.save()

    await update.message.reply_text(WELCOME_NEW, parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text(
        "*Step 1 of 3.* What's your sun sign?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_signs_keyboard(),
    )
    return ONB_SIGN


async def onb_pick_sign(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    sign = query.data.split(":", 2)[2]

    profile = Profile.load(user_id)
    profile.sun_sign = sign
    profile.save()

    await query.edit_message_text(f"☉ Sun sign saved: *{sign}*", parse_mode=ParseMode.MARKDOWN)
    await ctx.bot.send_message(
        chat_id=query.message.chat_id,
        text="*Step 2 of 3.* Where are you based? This grounds your readings in time.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_cities_keyboard(),
    )
    return ONB_CITY


async def onb_pick_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    payload = query.data.split(":", 2)[2]

    if payload == "_custom":
        await query.edit_message_text(
            "✏️  Type your city (e.g. `Kyiv, Ukraine`):", parse_mode=ParseMode.MARKDOWN
        )
        return ONB_CITY_CUSTOM

    profile = Profile.load(user_id)
    profile.birth_place = payload
    profile.save()
    await query.edit_message_text(f"🌍 Place saved: *{payload}*", parse_mode=ParseMode.MARKDOWN)
    return await _onb_next_after_city(update, ctx, user_id)


async def onb_city_custom(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = _user_id(update)
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Type a city name, please:")
        return ONB_CITY_CUSTOM
    profile = Profile.load(user_id)
    profile.birth_place = text
    profile.save()
    await update.message.reply_text(f"🌍 Place saved: *{text}*", parse_mode=ParseMode.MARKDOWN)
    return await _onb_next_after_city(update, ctx, user_id)


async def _onb_next_after_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    chat_id = update.effective_chat.id
    if cfg.is_owner(user_id):
        await ctx.bot.send_message(
            chat_id,
            "*Step 3 of 3 (owner only).* Which wallet should receive minted NFT cards?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_wallet_keyboard(),
        )
        return ONB_WALLET
    # Non-owners skip wallet (they can't mint anyway)
    await ctx.bot.send_message(chat_id, _onb_done_text(user_id), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def onb_pick_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    payload = query.data.split(":", 2)[2]
    profile = Profile.load(user_id)

    if payload == "_default":
        addr = _owner_default_wallet()
        profile.wallet_address = addr
        profile.save()
        await query.edit_message_text(f"🪙 Wallet saved: `{addr}`", parse_mode=ParseMode.MARKDOWN)
        await ctx.bot.send_message(query.message.chat_id, _onb_done_text(user_id),
                                    parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    if payload == "_skip":
        await query.edit_message_text("⏭  Wallet skipped — set it later with `/profile wallet 0x…`",
                                       parse_mode=ParseMode.MARKDOWN)
        await ctx.bot.send_message(query.message.chat_id, _onb_done_text(user_id),
                                    parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    # _custom
    await query.edit_message_text("✏️  Paste your wallet address (must start with 0x):",
                                   parse_mode=ParseMode.MARKDOWN)
    return ONB_WALLET  # next message is text


async def onb_wallet_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = _user_id(update)
    text = (update.message.text or "").strip()
    if not (text.startswith("0x") and len(text) == 42):
        await update.message.reply_text("That doesn't look like a wallet address. Paste a 0x… address (42 chars), or /cancel:")
        return ONB_WALLET
    profile = Profile.load(user_id)
    profile.wallet_address = text
    profile.save()
    await update.message.reply_text(f"🪙 Wallet saved: `{text}`", parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text(_onb_done_text(user_id), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


def _onb_done_text(user_id: int) -> str:
    profile = Profile.load(user_id)
    bits = []
    if profile.sun_sign:
        bits.append(f"☉ {profile.sun_sign}")
    if profile.birth_place:
        bits.append(f"🌍 {profile.birth_place}")
    if profile.wallet_address:
        bits.append(f"🪙 `{profile.wallet_address[:6]}…{profile.wallet_address[-4:]}`")
    summary = "  ·  ".join(bits) if bits else "(no profile yet)"
    return (
        f"✅ *Profile set:* {summary}\n\n"
        "Now ask the cards anything. Try sending a question like:\n"
        "  _“What does the next month want from me?”_\n\n"
        "Or use the menu (☰ next to the message field)."
    )


async def onb_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Onboarding cancelled. Use /start to begin again.")
    return ConversationHandler.END


# ----------------------------------------------------------------------
# Regular commands
# ----------------------------------------------------------------------

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_pull(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(ctx.args) if ctx.args else ""
    await _do_reading(update, ctx, question or "Speak to me about this moment.", spread="three_card")


async def cmd_single(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(ctx.args) if ctx.args else "What does this moment ask of me?"
    await _do_reading(update, ctx, question, spread="single")


async def cmd_horoscope(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update)
    sign = (ctx.args[0] if ctx.args else "").strip().capitalize()
    profile = Profile.load(user_id)
    sign = sign or (profile.sun_sign or "")
    if not sign:
        await update.message.reply_text(
            "Tell me your sun sign first: `/horoscope leo` (or run /start to set it).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    ok, refusal = _gate(user_id)
    if not ok:
        await update.message.reply_text(refusal or "Not now.", parse_mode=ParseMode.MARKDOWN)
        return
    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        text = await asyncio.to_thread(oracle_mod.daily_horoscope, sign, user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("horoscope failed")
        await update.message.reply_text(f"The Oracle stumbled: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return
    commit_read(user_id)
    await update.message.reply_text(f"☀️ *{sign} — today*\n\n{text}", parse_mode=ParseMode.MARKDOWN)


async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update)
    profile = Profile.load(user_id)
    if not ctx.args:
        body = "\n".join(f"{k}: {v}" for k, v in asdict(profile).items() if v) or "(empty)"
        await update.message.reply_text(
            f"*Your profile:*\n```\n{body}\n```\n"
            "Set fields:\n"
            "  `/profile sign leo`\n"
            "  `/profile dob 1995-04-12`\n"
            "  `/profile place \"Kyiv, Ukraine\"`\n"
            "  `/profile wallet 0xabc…`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    field, _, value = " ".join(ctx.args).partition(" ")
    field = field.lower().strip()
    value = value.strip().strip('"').strip("'")
    mapping = {
        "sign": "sun_sign", "dob": "dob", "place": "birth_place",
        "time": "birth_time", "name": "display_name",
        "wallet": "wallet_address", "tone": "tone_preference",
    }
    attr = mapping.get(field)
    if not attr:
        await update.message.reply_text(f"Unknown field `{field}`.", parse_mode=ParseMode.MARKDOWN)
        return
    setattr(profile, attr, value)
    profile.save()
    await update.message.reply_text(f"✓ {attr} = {value}", parse_mode=ParseMode.MARKDOWN)


async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update)
    rs = recent_readings(user_id, limit=5)
    if not rs:
        await update.message.reply_text("No readings yet. Send a question to begin.")
        return
    lines = [f"🕯️ *Your last {len(rs)} readings:*\n"]
    for r in rs:
        ts = time.strftime("%Y-%m-%d", time.gmtime(r.timestamp))
        cards = ", ".join(c["name"] for c in r.cards)
        lines.append(f"`{ts}` — _{r.question[:60]}_\n      {cards}\n")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update)
    if not cfg.is_owner(user_id):
        return
    g = todays_spend()
    msg = (
        f"*{BRAND} — status*\n"
        f"Today's spend: ${g.spent_usd:.4f} / ${cfg.max_daily_usd_spend}\n"
        f"Breakdown: {g.breakdown}\n"
        f"Public enabled: {cfg.public_enabled}\n"
        f"Public daily / lifetime: {cfg.public_daily_readings} / {cfg.public_lifetime_readings}\n"
        f"Allowlist daily: {cfg.allowlist_daily_readings}\n"
        f"Owner: {cfg.owner_telegram_id}\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ----------------------------------------------------------------------
# Free-form text -> reading
# ----------------------------------------------------------------------

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    q = update.message.text.strip()
    if q.startswith("/"):
        return
    await _do_reading(update, ctx, q, spread="three_card")


# ----------------------------------------------------------------------
# Reading flow
# ----------------------------------------------------------------------

THINKING = "🕯️ _Drawing the cards..._"
INTERPRETING = "🌙 _The oracle is reading your question..._"


async def _do_reading(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    question: str,
    *,
    spread: str = "three_card",
) -> None:
    user_id = _user_id(update)
    chat_id = update.effective_chat.id

    ok, refusal = _gate(user_id)
    if not ok:
        await update.message.reply_text(refusal or "Not now.", parse_mode=ParseMode.MARKDOWN)
        return

    log.info("reading: user=%s spread=%s q=%r", _user_label(update), spread, question[:80])
    await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
    progress_msg = await update.message.reply_text(THINKING, parse_mode=ParseMode.MARKDOWN)

    try:
        drawn = await asyncio.to_thread(oracle_mod.pull_cards, user_id, question, spread)
        rendered = await asyncio.to_thread(oracle_mod.render_cards, drawn["cards"])
    except Exception as e:  # noqa: BLE001
        log.exception("pull/render failed")
        await progress_msg.edit_text(f"The cards are uncooperative: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return

    caption = f"*“{question}”*\n_{spread.replace('_', ' ')}_"
    media: list[InputMediaPhoto] = []
    for i, c in enumerate(rendered):
        path = Path(c["image_path"])
        with path.open("rb") as f:
            data = f.read()
        if i == 0:
            media.append(InputMediaPhoto(media=data, caption=caption,
                                         parse_mode=ParseMode.MARKDOWN, filename=path.name))
        else:
            media.append(InputMediaPhoto(media=data, filename=path.name))
    try:
        await ctx.bot.send_media_group(chat_id=chat_id, media=media)
    except Exception:
        log.exception("media_group failed; falling back to single sends")
        for c in rendered:
            with Path(c["image_path"]).open("rb") as f:
                await ctx.bot.send_photo(chat_id=chat_id, photo=f.read())

    await progress_msg.edit_text(INTERPRETING, parse_mode=ParseMode.MARKDOWN)
    try:
        interpretation = await asyncio.to_thread(
            oracle_mod.interpret_reading, user_id, question, rendered, spread
        )
    except Exception as e:  # noqa: BLE001
        log.exception("interpret failed")
        await progress_msg.edit_text(f"The oracle is silent: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return

    reading = Reading(
        id=Reading.new_id(),
        user_id=str(user_id),
        timestamp=time.time(),
        question=question,
        spread=spread,
        cards=rendered,
        interpretation=interpretation,
    )
    append_reading(reading)
    commit_read(user_id)

    await progress_msg.delete()
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=interpretation,
        reply_markup=_reading_keyboard(user_id, reading.id),
    )


# ----------------------------------------------------------------------
# Inline buttons (non-onboarding)
# ----------------------------------------------------------------------

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    # Onboarding callbacks are handled by ConversationHandler; ignore them here.
    if query.data.startswith("onb:"):
        return
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "pull_again":
        msg = update.effective_message
        last = recent_readings(user_id, limit=1)
        question = last[-1].question if last else "Pull again."
        await ctx.bot.send_message(msg.chat_id, "🕯️ _New cards..._", parse_mode=ParseMode.MARKDOWN)
        try:
            ok, refusal = _gate(user_id)
            if not ok:
                await ctx.bot.send_message(msg.chat_id, refusal or "Not now.")
                return
            drawn = await asyncio.to_thread(oracle_mod.pull_cards, user_id, question, "three_card")
            rendered = await asyncio.to_thread(oracle_mod.render_cards, drawn["cards"])
            interpretation = await asyncio.to_thread(
                oracle_mod.interpret_reading, user_id, question, rendered, "three_card"
            )
            r = Reading(id=Reading.new_id(), user_id=str(user_id), timestamp=time.time(),
                        question=question, spread="three_card",
                        cards=rendered, interpretation=interpretation)
            append_reading(r)
            commit_read(user_id)
            media = []
            for i, c in enumerate(rendered):
                with open(c["image_path"], "rb") as f:
                    data_b = f.read()
                if i == 0:
                    media.append(InputMediaPhoto(media=data_b, caption=f"*“{question}”*",
                                                 parse_mode=ParseMode.MARKDOWN))
                else:
                    media.append(InputMediaPhoto(media=data_b))
            await ctx.bot.send_media_group(msg.chat_id, media=media)
            await ctx.bot.send_message(msg.chat_id, interpretation,
                                       reply_markup=_reading_keyboard(user_id, r.id))
        except Exception as e:  # noqa: BLE001
            log.exception("pull_again failed")
            await ctx.bot.send_message(msg.chat_id, f"The cards resist: `{e}`",
                                        parse_mode=ParseMode.MARKDOWN)
        return

    if data == "schedule_daily":
        profile = Profile.load(user_id)
        if not profile.sun_sign:
            await ctx.bot.send_message(query.message.chat_id,
                "Set your sun sign first: `/profile sign leo` (or run /start).",
                parse_mode=ParseMode.MARKDOWN)
            return
        chat_id = query.message.chat_id
        for job in ctx.job_queue.get_jobs_by_name(f"daily-{user_id}"):
            job.schedule_removal()
        ctx.job_queue.run_daily(
            _job_daily_horoscope,
            time=dtime(hour=9, minute=0),
            data={"user_id": user_id, "chat_id": chat_id},
            name=f"daily-{user_id}",
        )
        await ctx.bot.send_message(chat_id,
            f"📅 _Done. The {profile.sun_sign} horoscope arrives every morning at 09:00 UTC._",
            parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("mint:"):
        _, reading_id, idx = data.split(":", 2)
        decision = can_mint(user_id)
        if not decision.allowed:
            await ctx.bot.send_message(query.message.chat_id, decision.user_message,
                                        parse_mode=ParseMode.MARKDOWN)
            return

        # Owner-friendly: if they didn't set a wallet during onboarding, fall back
        # to the deployer wallet so the mint always works in demo.
        profile = Profile.load(user_id)
        if not profile.wallet_address:
            default = _owner_default_wallet()
            if default:
                profile.wallet_address = default
                profile.save()
                await ctx.bot.send_message(query.message.chat_id,
                    f"_(no wallet set; using server wallet `{default[:6]}…{default[-4:]}` — change with `/profile wallet 0x…`)_",
                    parse_mode=ParseMode.MARKDOWN)

        await ctx.bot.send_message(query.message.chat_id,
            "⛓️ _Pinning to IPFS and minting on Base Sepolia (≈ 10 s)..._",
            parse_mode=ParseMode.MARKDOWN)
        try:
            result = await asyncio.to_thread(oracle_mod.mint_card, user_id, reading_id, int(idx))
        except Exception as e:  # noqa: BLE001
            log.exception("mint failed")
            await ctx.bot.send_message(query.message.chat_id, f"Mint failed: `{e}`",
                                        parse_mode=ParseMode.MARKDOWN)
            return

        # Pull the card name for a friendlier confirmation
        reading = find_reading(user_id, reading_id)
        card_name = reading.cards[int(idx)]["name"] if reading and reading.cards else "card"

        await ctx.bot.send_message(
            query.message.chat_id,
            f"✨ *Minted on Base Sepolia.*\n"
            f"*{card_name}* → token #{result['token_id']}\n\n"
            f"🃏 [View your card]({result['viewer_url']})\n"
            f"🔗 [Basescan token]({result['basescan_token_url']}) · [Tx]({result['tx_url']})",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )


# ----------------------------------------------------------------------
# Scheduled job
# ----------------------------------------------------------------------

async def _job_daily_horoscope(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    data = ctx.job.data or {}
    user_id = int(data["user_id"])
    chat_id = int(data["chat_id"])
    profile = Profile.load(user_id)
    sign = profile.sun_sign or "Aries"
    try:
        text = await asyncio.to_thread(oracle_mod.daily_horoscope, sign, user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("scheduled horoscope failed for %s", user_id)
        await ctx.bot.send_message(chat_id, f"_Today's horoscope stumbled: {e}_",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    await ctx.bot.send_message(chat_id, f"☀️ *{sign} — today*\n\n{text}",
                                parse_mode=ParseMode.MARKDOWN)


# ----------------------------------------------------------------------
# Wiring
# ----------------------------------------------------------------------

async def _post_init(app: Application) -> None:
    """Set the BotCommands menu once the bot starts."""
    try:
        await app.bot.set_my_commands(COMMANDS_MENU, scope=BotCommandScopeAllPrivateChats())
        await app.bot.set_my_short_description(
            f"{BRAND} — {TAGLINE}. Powered by Hermes Agent + Kimi K2.6."
        )
        await app.bot.set_my_description(
            f"🪞 {BRAND}\n\n"
            f"{TAGLINE.capitalize()}.\n\n"
            "Send a question and the cards will answer. Built for the Hermes Agent "
            "Creative Hackathon (Nous Research × Kimi).\n\n"
            "github.com/dream0x/Hermes-Tarot"
        )
        log.info("BotCommands menu + descriptions registered")
    except Exception:  # noqa: BLE001
        log.exception("failed to register BotCommands menu")


def build_app() -> Application:
    if not cfg.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set")
    app = ApplicationBuilder().token(cfg.telegram_bot_token).post_init(_post_init).build()

    # Onboarding wizard — entered only via /start when user is new
    onboarding = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            ONB_SIGN: [CallbackQueryHandler(onb_pick_sign, pattern=r"^onb:sign:")],
            ONB_CITY: [CallbackQueryHandler(onb_pick_city, pattern=r"^onb:city:")],
            ONB_CITY_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_city_custom)],
            ONB_WALLET: [
                CallbackQueryHandler(onb_pick_wallet, pattern=r"^onb:wallet:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, onb_wallet_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", onb_cancel)],
        allow_reentry=True,
    )
    app.add_handler(onboarding)

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("pull", cmd_pull))
    app.add_handler(CommandHandler("single", cmd_single))
    app.add_handler(CommandHandler("horoscope", cmd_horoscope))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main() -> None:
    app = build_app()
    log.info("Starting %s bot @%s ...", BRAND, cfg.telegram_bot_username or "<unknown>")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
