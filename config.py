"""
config.py — Central configuration
All other files import from here. Secrets are read from .env
"""
from dotenv import load_dotenv
import os

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = int(os.getenv("CHAT_ID", "0"))

# ── NewsAPI ───────────────────────────────────────────────────────────────────
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# ── Stocks ────────────────────────────────────────────────────────────────────
STOCKS = {
    "EMBASSY": "EMBASSY.NS",
    "BIRET":   "BIRET.NS",
}

NEWS_QUERIES = {
    "EMBASSY": "Embassy Office Parks REIT",
    "BIRET":   "Brookfield India Real Estate Trust REIT",
}

MACRO_QUERY = "India REIT real estate interest rate RBI"

# ── Agent rules ───────────────────────────────────────────────────────────────
MONTHLY_CAP   = int(os.getenv("MONTHLY_CAP",   "5000"))
MIN_ORDER     = int(os.getenv("MIN_ORDER",      "500"))
BUY_THRESHOLD = int(os.getenv("BUY_THRESHOLD",  "4"))

# ── Schedule (UTC) ────────────────────────────────────────────────────────────
# 18:30 IST = 13:00 UTC
RUN_HOUR_UTC   = int(os.getenv("RUN_HOUR_UTC",   "13"))
RUN_MINUTE_UTC = int(os.getenv("RUN_MINUTE_UTC", "0"))

# ── Google Drive ──────────────────────────────────────────────────────────────
GDRIVE_SHEET_ID = os.getenv("GDRIVE_SHEET_ID")
