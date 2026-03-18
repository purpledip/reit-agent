"""
indicators.py — Technical indicators + news sentiment scoring
"""
import pandas as pd
import numpy as np


# ── Technical indicators ──────────────────────────────────────────────────────

def sma(df: pd.DataFrame, window: int) -> pd.Series:
    return df["Close"].squeeze().rolling(window=window).mean()


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    close = df["Close"].squeeze()
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))


def macd(df: pd.DataFrame):
    """Returns (macd_line, signal_line) as pd.Series."""
    close      = df["Close"].squeeze()
    ema12      = close.ewm(span=12, adjust=False).mean()
    ema26      = close.ewm(span=26, adjust=False).mean()
    macd_line  = ema12 - ema26
    signal_line= macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, signal_line


# ── Sentiment scoring ─────────────────────────────────────────────────────────

BULLISH_WORDS = [
    "upgrade", "buy", "strong", "dividend", "distribution",
    "growth", "leased", "occupancy", "acquisition", "positive",
    "beat", "record", "outperform", "rate cut", "rbi cut",
    "expansion", "profit", "revenue", "demand", "recovery",
]

BEARISH_WORDS = [
    "downgrade", "sell", "weak", "vacancy", "default", "loss",
    "exit", "rate hike", "concern", "miss", "below", "decline",
    "resign", "regulatory", "sebi", "probe", "slowdown",
    "lawsuit", "dispute", "debt", "risk", "penalty",
]


def sentiment_score(articles: list) -> int:
    """
    Score news sentiment from -5 to +5.
    Positive = bullish news, Negative = bearish news.
    """
    score = 0
    for article in articles:
        title = article.get("title", "") or ""
        desc  = article.get("description", "") or ""
        text  = (title + " " + desc).lower()
        for word in BULLISH_WORDS:
            if word in text:
                score += 1
        for word in BEARISH_WORDS:
            if word in text:
                score -= 1
    return max(-5, min(5, score))
