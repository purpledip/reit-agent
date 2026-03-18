"""
bot.py — Telegram bot
Sends recommendations with inline buttons, handles buy/skip acknowledgements,
updates purchases.csv only after user confirms, and provides /status + /history commands.
"""
import datetime
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from budget  import log_purchase, budget_summary, get_remaining_budget
from config  import BOT_TOKEN, CHAT_ID, MIN_ORDER

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── In-memory store for the pending recommendation ───────────────────────────
_pending: dict = {}


# ═══════════════════════════════════════════════════════════════
#  SEND RECOMMENDATION
# ═══════════════════════════════════════════════════════════════

async def send_recommendation(
    app: Application,
    allocation: dict,
    embassy: dict,
    biret: dict,
    macro_articles: list,
) -> None:
    """
    Called by agent.py after scoring. Sends message + inline buttons to CHAT_ID.
    If skip=True, sends info-only message with no buttons.
    """
    global _pending

    text = _build_message(allocation, embassy, biret, macro_articles)

    if allocation["skip"]:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )
        return

    # Store pending so the callback handler can reference prices
    _pending = {
        "embassy_amt":   allocation["embassy_amt"],
        "biret_amt":     allocation["biret_amt"],
        "embassy_price": embassy["price"],
        "biret_price":   biret["price"],
    }

    keyboard = _build_keyboard(allocation)
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ═══════════════════════════════════════════════════════════════
#  CALLBACK: BUTTON TAPS
# ═══════════════════════════════════════════════════════════════

async def handle_ack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the user tapping one of the four inline buttons."""
    global _pending
    query = update.callback_query

    # Always answer the callback to remove the loading spinner on the button
    try:
        await query.answer()
    except BadRequest:
        pass  # already answered — safe to ignore

    if not _pending:
        # Buttons are stale (e.g. bot restarted) — remove them cleanly
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        await query.message.reply_text(
            "⚠️ No pending recommendation found — the bot may have restarted. "
            "Wait for the next daily signal."
        )
        return

    p      = _pending.copy()
    choice = query.data

    # ── Log the action ────────────────────────────────────────────────────────
    if choice == "bought_both":
        log_purchase(p["embassy_amt"], p["biret_amt"], p["embassy_price"], p["biret_price"])
        actual_e, actual_b = p["embassy_amt"], p["biret_amt"]

    elif choice == "bought_embassy":
        log_purchase(p["embassy_amt"], 0, p["embassy_price"], p["biret_price"])
        actual_e, actual_b = p["embassy_amt"], 0

    elif choice == "bought_biret":
        log_purchase(0, p["biret_amt"], p["embassy_price"], p["biret_price"])
        actual_e, actual_b = 0, p["biret_amt"]

    elif choice == "skipped_both":
        log_purchase(0, 0, p["embassy_price"], p["biret_price"], skipped=True)
        actual_e, actual_b = 0, 0

    else:
        await query.message.reply_text("⚠️ Unknown action — please wait for the next signal.")
        return

    # Clear pending state
    _pending = {}

    # ── Remove inline buttons from the original message ───────────────────────
    # Wrapped in try/except — Telegram raises BadRequest if buttons are already
    # gone (e.g. duplicate tap, network retry). Safe to ignore.
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest as e:
        logger.warning(f"Could not remove buttons: {e}")

    # ── Send confirmation reply ───────────────────────────────────────────────
    conf = _build_confirmation(choice, actual_e, actual_b, p)
    await query.message.reply_text(conf, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — live budget summary for the current month."""
    b    = budget_summary()
    bars = int(b["pct_used"] / 10)
    bar  = "█" * bars + "░" * (10 - bars)

    msg = (
        f"📊 *Monthly Budget — {datetime.date.today().strftime('%B %Y')}*\n\n"
        f"`{bar}` {b['pct_used']}%\n\n"
        f"EMBASSY invested:  ₹{b['spent_embassy']:,.0f}\n"
        f"BIRET invested:    ₹{b['spent_biret']:,.0f}\n"
        f"──────────────────────\n"
        f"Total spent:       ₹{b['total_spent']:,.0f} / ₹{b['cap']:,}\n"
        f"Remaining:         ₹{b['remaining']:,.0f}\n"
    )
    if b["remaining"] < MIN_ORDER:
        msg += "\n⚠️ _Below minimum order. Agent will pause until next month._"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/history — last 15 transactions."""
    import csv, os
    from config import LOG_FILE

    if not os.path.exists(LOG_FILE):
        await update.message.reply_text("No transactions logged yet.")
        return

    with open(LOG_FILE, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        await update.message.reply_text("No transactions logged yet.")
        return

    recent = rows[-15:][::-1]   # last 15, newest first
    lines  = ["📋 *Last 15 transactions*\n"]

    for r in recent:
        date_str = r.get("date", "?")
        e_amt    = float(r.get("embassy_amt", 0))
        b_amt    = float(r.get("biret_amt",   0))
        skipped  = r.get("skipped", "no") == "yes"

        if skipped or (e_amt == 0 and b_amt == 0):
            lines.append(f"`{date_str}` — ⏭ skipped")
        else:
            parts = []
            if e_amt > 0: parts.append(f"EMBASSY ₹{e_amt:.0f}")
            if b_amt > 0: parts.append(f"BIRET ₹{b_amt:.0f}")
            total = e_amt + b_amt
            lines.append(f"`{date_str}` — {' + '.join(parts)}  *(₹{total:.0f})*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — list commands."""
    msg = (
        "📖 *REIT Agent Commands*\n\n"
        "/status   — Monthly budget summary\n"
        "/history  — Last 15 transactions\n"
        "/help     — This message\n\n"
        "_The agent sends a recommendation every weekday at 6:30 PM IST. "
        "Tap a button to confirm or skip._"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════
#  BUILDER HELPERS
# ═══════════════════════════════════════════════════════════════

def _sentiment_emoji(score: int) -> str:
    if score >= 2:  return "🟢"
    if score <= -2: return "🔴"
    return "🟡"


def _build_message(allocation, embassy, biret, macro_articles) -> str:
    b   = budget_summary()
    s_e = _sentiment_emoji(embassy.get("sentiment", 0))
    s_b = _sentiment_emoji(biret.get("sentiment", 0))

    budget_line = (
        f"💼 Budget: ₹{b['total_spent']:.0f} used / ₹{b['cap']:,}  "
        f"(₹{b['remaining']:.0f} remaining)\n"
    )

    if allocation["skip"]:
        lines = [
            "📊 *Daily REIT Check — No Purchase Today*\n",
            budget_line,
            f"_{allocation['reason']}_\n",
            f"EMBASSY {s_e}  ₹{embassy['price']:.2f}  score {embassy.get('score', 0)}/10",
            f"BIRET   {s_b}  ₹{biret['price']:.2f}  score {biret.get('score', 0)}/10",
        ]
        return "\n".join(lines)

    lines = ["📈 *REIT Buy Alert*\n", budget_line]

    lines.append(
        f"\n*EMBASSY* {s_e}  ₹{embassy['price']:.2f}  score {embassy.get('score', 0)}/10"
    )
    for h in embassy.get("headlines", [])[:3]:
        lines.append(f"  • {h[:80]}")

    lines.append(
        f"\n*BIRET* {s_b}  ₹{biret['price']:.2f}  score {biret.get('score', 0)}/10"
    )
    for h in biret.get("headlines", [])[:3]:
        lines.append(f"  • {h[:80]}")

    lines.append(f"\n💰 *Recommended allocation*")
    lines.append(f"_{allocation['reason']}_")
    if allocation["embassy_amt"] > 0:
        lines.append(f"  → Buy EMBASSY: ₹{allocation['embassy_amt']:,}")
    else:
        lines.append(f"  → EMBASSY: skip")
    if allocation["biret_amt"] > 0:
        lines.append(f"  → Buy BIRET:   ₹{allocation['biret_amt']:,}")
    else:
        lines.append(f"  → BIRET: skip")

    if macro_articles:
        lines.append("\n🌐 *Macro news*")
        for a in macro_articles[:2]:
            lines.append(f"  • {(a.get('title') or '')[:80]}")

    lines.append("\n_Tap a button below to confirm or skip_")
    return "\n".join(lines)


def _build_keyboard(allocation: dict) -> list:
    e = allocation["embassy_amt"]
    b = allocation["biret_amt"]

    if e > 0 and b > 0:
        return [
            [InlineKeyboardButton(f"✅ Bought both (₹{e+b:,})", callback_data="bought_both")],
            [
                InlineKeyboardButton(f"✅ EMBASSY only ₹{e:,}", callback_data="bought_embassy"),
                InlineKeyboardButton(f"✅ BIRET only ₹{b:,}",   callback_data="bought_biret"),
            ],
            [InlineKeyboardButton("⏭ Skipped both", callback_data="skipped_both")],
        ]
    elif e > 0:
        return [[
            InlineKeyboardButton(f"✅ Bought EMBASSY ₹{e:,}", callback_data="bought_embassy"),
            InlineKeyboardButton("⏭ Skipped",                  callback_data="skipped_both"),
        ]]
    else:
        return [[
            InlineKeyboardButton(f"✅ Bought BIRET ₹{b:,}", callback_data="bought_biret"),
            InlineKeyboardButton("⏭ Skipped",                callback_data="skipped_both"),
        ]]


def _build_confirmation(choice: str, actual_e: int, actual_b: int, p: dict) -> str:
    b = budget_summary()

    if choice == "skipped_both":
        return (
            f"⏭ *Skipped — logged as skipped.*\n\n"
            f"Monthly spend stays at ₹{b['total_spent']:,.0f}.\n"
            f"₹{b['remaining']:,.0f} still available this month."
        )

    lines = ["✅ *Purchase logged!*\n"]
    if actual_e > 0 and p["embassy_price"] > 0:
        units = actual_e / p["embassy_price"]
        lines.append(f"EMBASSY: ₹{actual_e:,}  (~{units:.3f} units @ ₹{p['embassy_price']:.2f})")
    if actual_b > 0 and p["biret_price"] > 0:
        units = actual_b / p["biret_price"]
        lines.append(f"BIRET:   ₹{actual_b:,}  (~{units:.3f} units @ ₹{p['biret_price']:.2f})")

    lines.append(f"\n💼 ₹{b['total_spent']:,.0f} spent this month / ₹{b['cap']:,}")
    lines.append(f"₹{b['remaining']:,.0f} remaining")

    if b["remaining"] <= 0:
        lines.append("\n🎯 _Monthly cap reached! No more buys this month._")
    elif b["remaining"] < MIN_ORDER:
        lines.append(
            f"\n⚠️ _Only ₹{b['remaining']:.0f} left — below minimum. "
            "Agent will pause until next month._"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  REGISTER HANDLERS (called from agent.py)
# ═══════════════════════════════════════════════════════════════

def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("status",  status_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("help",    help_command))
    app.add_handler(CallbackQueryHandler(handle_ack))