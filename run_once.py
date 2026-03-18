"""
run_once.py — Single-shot runner for GitHub Actions / cron deployments.
Runs the analysis once, sends the Telegram message, then exits.
Use this instead of agent.py when deploying via GitHub Actions.

For local / always-on server use: python agent.py (includes polling loop)
"""
import asyncio
import logging
from telegram.ext import Application
from config     import BOT_TOKEN
from data       import fetch_all
from news       import fetch_all_news
from indicators import sentiment_score
from signals    import score_stock, allocate
from bot        import send_recommendation

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set. Check your .env / GitHub secrets.")

    app = Application.builder().token(BOT_TOKEN).build()
    await app.initialize()

    stock_data = fetch_all()
    all_news   = fetch_all_news()

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
        logger.info(f"{name}: ₹{data['price']:.2f}  score={score}/10")

    allocation = allocate(
        results["EMBASSY"]["score"],
        results["BIRET"]["score"],
    )
    logger.info(f"Allocation: {allocation}")

    await send_recommendation(
        app,
        allocation,
        results["EMBASSY"],
        results["BIRET"],
        all_news.get("macro", []),
    )
    logger.info("Done.")
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
