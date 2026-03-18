"""
agent.py — Main entry point
Schedules the daily analysis job and runs the Telegram bot event loop.
Start with: python agent.py
"""
import asyncio
import datetime
import logging

from telegram.ext import Application

from config     import BOT_TOKEN, RUN_HOUR_UTC, RUN_MINUTE_UTC
from data       import fetch_all
from news       import fetch_all_news
from indicators import sentiment_score
from signals    import score_stock, allocate
from bot        import send_recommendation, register_handlers

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  CORE ANALYSIS JOB
# ═══════════════════════════════════════════════════════════════

async def run_analysis(app: Application) -> None:
    """
    Full pipeline:
    1. Fetch prices + history
    2. Fetch news
    3. Score each stock
    4. Compute allocation
    5. Send Telegram recommendation with buttons
    """
    logger.info("Running daily analysis...")

    # ── Step 1: stock data ────────────────────────────────────────────────────
    stock_data  = fetch_all()           # { "EMBASSY": {ticker, history, price}, ... }

    # ── Step 2: news ──────────────────────────────────────────────────────────
    all_news    = fetch_all_news()      # { "EMBASSY": [...], "BIRET": [...], "macro": [...] }

    # ── Step 3: score ─────────────────────────────────────────────────────────
    results = {}
    for name, data in stock_data.items():
        articles = all_news.get(name, [])
        score    = score_stock(data["history"], articles)
        results[name] = {
            "price":     data["price"],
            "score":     score,
            "sentiment": sentiment_score(articles),
            "headlines": [a.get("title", "") for a in articles[:3] if a.get("title")],
        }
        logger.info(f"  {name}: price=₹{data['price']:.2f}  score={score}/10")

    # ── Step 4: allocate ──────────────────────────────────────────────────────
    allocation = allocate(
        results["EMBASSY"]["score"],
        results["BIRET"]["score"],
    )
    logger.info(f"  Allocation: EMBASSY=₹{allocation['embassy_amt']} "
                f"BIRET=₹{allocation['biret_amt']} skip={allocation['skip']}")
    logger.info(f"  Reason: {allocation['reason']}")

    # ── Step 5: send to Telegram ──────────────────────────────────────────────
    await send_recommendation(
        app,
        allocation,
        results["EMBASSY"],
        results["BIRET"],
        all_news.get("macro", []),
    )
    logger.info("  Recommendation sent.")


# ═══════════════════════════════════════════════════════════════
#  SCHEDULER CALLBACK (wraps async job for job_queue)
# ═══════════════════════════════════════════════════════════════

def _make_job(app: Application):
    async def job(context):
        try:
            await run_analysis(app)
        except Exception as e:
            logger.error(f"Analysis job failed: {e}", exc_info=True)
    return job


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set. Check your .env file.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Register Telegram command + button handlers
    register_handlers(app)

    # Schedule daily job (Mon–Fri at RUN_HOUR_UTC:RUN_MINUTE_UTC UTC = 6:30 PM IST)
    run_time = datetime.time(
        hour=RUN_HOUR_UTC,
        minute=RUN_MINUTE_UTC,
        tzinfo=datetime.timezone.utc,
    )
    days = (1, 2, 3, 4, 5)  # Monday–Friday
    for day in days:
        app.job_queue.run_daily(
            _make_job(app),
            time=run_time,
            days=(day,),
        )

    logger.info(
        f"Agent started. Daily job at {RUN_HOUR_UTC:02d}:{RUN_MINUTE_UTC:02d} UTC "
        f"(Mon–Fri). Send /help on Telegram."
    )
    app.run_polling()


if __name__ == "__main__":
    main()
