"""
data.py — Stock data fetching via yFinance
"""
import yfinance as yf
import pandas as pd
from config import STOCKS


def fetch_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Download OHLCV history for a ticker. Returns empty DataFrame on failure."""
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"[data] Failed to fetch history for {ticker}: {e}")
        return pd.DataFrame()


def fetch_current_price(ticker: str) -> float:
    """Return latest market price. Falls back to last close on failure."""
    try:
        info = yf.Ticker(ticker).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price:
            return float(price)
    except Exception:
        pass
    # Fallback: last close from 5-day history
    try:
        df = yf.download(ticker, period="5d", interval="1d", progress=False)
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return 0.0


def fetch_all() -> dict:
    """
    Fetch history + current price for all configured stocks.
    Returns dict keyed by stock name:
        { "EMBASSY": {"ticker": ..., "history": df, "price": float}, ... }
    """
    results = {}
    for name, ticker in STOCKS.items():
        results[name] = {
            "ticker":  ticker,
            "history": fetch_history(ticker),
            "price":   fetch_current_price(ticker),
        }
    return results
