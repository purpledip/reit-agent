"""
signals.py — Buy signal scoring and ₹ allocation engine
Handles all edge cases: budget exhausted, below minimum, one stock qualifies,
neither qualifies, rounding, and sub-minimum splits.
"""
import pandas as pd
from indicators import rsi, macd, sma, sentiment_score
from budget     import get_remaining_budget
from config     import MIN_ORDER, BUY_THRESHOLD


def _round_down(amount: float, step: int = 10) -> int:
    """Round down to nearest ₹10 — clean, exchange-friendly order sizes."""
    return (int(amount) // step) * step


def score_stock(df: pd.DataFrame, articles: list) -> int:
    """
    Score a stock 0–10 based on technical signals + news sentiment.

    Technical (max 8):
        RSI < 45  →  +2    (oversold entry)
        RSI < 35  →  +1    (extra: strongly oversold)
        MACD bullish crossover → +3
        Price within 2% of SMA50 (support zone) → +2

    Sentiment (−2 to +2):
        news_score >= 2  → +2
        news_score >= 1  → +1
        news_score <= −1 → −1
        news_score <= −2 → −2
    """
    if df.empty or len(df) < 30:
        return 0

    score = 0

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi_vals = rsi(df)
    if rsi_vals.empty:
        return 0
    r = float(rsi_vals.iloc[-1])
    if r < 45:
        score += 2
    if r < 35:
        score += 1

    # ── MACD crossover ────────────────────────────────────────────────────────
    macd_line, signal_line = macd(df)
    if (
        float(macd_line.iloc[-1])   > float(signal_line.iloc[-1]) and
        float(macd_line.iloc[-2])   < float(signal_line.iloc[-2])
    ):
        score += 3

    # ── Price vs SMA50 ────────────────────────────────────────────────────────
    sma50 = sma(df, 50)
    if not sma50.empty and float(sma50.iloc[-1]) > 0:
        price = float(df["Close"].squeeze().iloc[-1])
        if price < float(sma50.iloc[-1]) * 1.02:
            score += 2

    # ── News sentiment ────────────────────────────────────────────────────────
    ns = sentiment_score(articles)
    if ns >= 2:
        score += 2
    elif ns >= 1:
        score += 1
    elif ns <= -2:
        score -= 2
    elif ns <= -1:
        score -= 1

    return max(0, min(10, score))


def allocate(score_embassy: int, score_biret: int) -> dict:
    """
    Decide how to split the remaining monthly budget between the two stocks.

    Returns a dict:
    {
        "embassy_amt": int,      # rupees to invest in EMBASSY (0 = skip)
        "biret_amt":   int,      # rupees to invest in BIRET   (0 = skip)
        "skip":        bool,     # True  = don't buy anything today
        "reason":      str,      # human-readable explanation
    }

    Edge cases handled:
        1. Monthly cap fully exhausted
        2. Remaining < MIN_ORDER
        3. Neither stock meets BUY_THRESHOLD
        4. Only one stock qualifies
        5. Proportional split produces sub-MIN_ORDER share → consolidate
        6. After rounding, both amounts are 0 → give all to stronger stock
    """
    remaining = get_remaining_budget()

    # ── Edge case 1: budget fully used ───────────────────────────────────────
    if remaining <= 0:
        return {
            "embassy_amt": 0,
            "biret_amt":   0,
            "skip":        True,
            "reason":      "Monthly cap of ₹{:,} fully used. No more buys this month.".format(
                            5000
                           ),
        }

    # ── Edge case 2: remaining too small for any order ────────────────────────
    if remaining < MIN_ORDER:
        return {
            "embassy_amt": 0,
            "biret_amt":   0,
            "skip":        True,
            "reason":      f"Only ₹{remaining:.0f} left — below minimum order ₹{MIN_ORDER}. "
                            "Saving remainder for next month.",
        }

    e_ok = score_embassy >= BUY_THRESHOLD
    b_ok = score_biret   >= BUY_THRESHOLD

    # ── Edge case 3: neither qualifies ───────────────────────────────────────
    if not e_ok and not b_ok:
        return {
            "embassy_amt": 0,
            "biret_amt":   0,
            "skip":        True,
            "reason":      (
                f"No buy signal today. "
                f"EMBASSY score {score_embassy}/10, "
                f"BIRET score {score_biret}/10 "
                f"(threshold {BUY_THRESHOLD}/10)."
            ),
        }

    # ── Edge case 4a: only EMBASSY qualifies ─────────────────────────────────
    if e_ok and not b_ok:
        return {
            "embassy_amt": _round_down(remaining),
            "biret_amt":   0,
            "skip":        False,
            "reason":      (
                f"EMBASSY qualifies (score {score_embassy}/10). "
                f"BIRET score {score_biret}/10 too low — all budget to EMBASSY."
            ),
        }

    # ── Edge case 4b: only BIRET qualifies ───────────────────────────────────
    if b_ok and not e_ok:
        return {
            "embassy_amt": 0,
            "biret_amt":   _round_down(remaining),
            "skip":        False,
            "reason":      (
                f"BIRET qualifies (score {score_biret}/10). "
                f"EMBASSY score {score_embassy}/10 too low — all budget to BIRET."
            ),
        }

    # ── Both qualify: proportional split by score ─────────────────────────────
    total_score = score_embassy + score_biret
    raw_e = (score_embassy / total_score) * remaining
    raw_b = remaining - raw_e
    e_amt = _round_down(raw_e)
    b_amt = _round_down(raw_b)

    # ── Edge case 5: split produces sub-minimum for one side ─────────────────
    if e_amt < MIN_ORDER and b_amt < MIN_ORDER:
        # Not enough to split at all — give all to stronger stock
        if score_embassy >= score_biret:
            return {
                "embassy_amt": _round_down(remaining),
                "biret_amt":   0,
                "skip":        False,
                "reason":      (
                    "Budget too small to split between both stocks. "
                    "All allocated to EMBASSY (higher score)."
                ),
            }
        else:
            return {
                "embassy_amt": 0,
                "biret_amt":   _round_down(remaining),
                "skip":        False,
                "reason":      (
                    "Budget too small to split between both stocks. "
                    "All allocated to BIRET (higher score)."
                ),
            }

    if e_amt < MIN_ORDER:
        # EMBASSY share too small — redirect to BIRET
        return {
            "embassy_amt": 0,
            "biret_amt":   _round_down(remaining),
            "skip":        False,
            "reason":      (
                f"EMBASSY proportional share ₹{e_amt} below minimum ₹{MIN_ORDER}. "
                "Redirected to BIRET."
            ),
        }

    if b_amt < MIN_ORDER:
        # BIRET share too small — redirect to EMBASSY
        return {
            "embassy_amt": _round_down(remaining),
            "biret_amt":   0,
            "skip":        False,
            "reason":      (
                f"BIRET proportional share ₹{b_amt} below minimum ₹{MIN_ORDER}. "
                "Redirected to EMBASSY."
            ),
        }

    # ── Edge case 6: rounding zeroed out amounts ──────────────────────────────
    if e_amt == 0 and b_amt == 0:
        winner = "EMBASSY" if score_embassy >= score_biret else "BIRET"
        return {
            "embassy_amt": _round_down(remaining) if winner == "EMBASSY" else 0,
            "biret_amt":   _round_down(remaining) if winner == "BIRET"   else 0,
            "skip":        False,
            "reason":      f"Rounding reduced both shares to ₹0. All budget to {winner}.",
        }

    # ── Normal proportional split ─────────────────────────────────────────────
    return {
        "embassy_amt": e_amt,
        "biret_amt":   b_amt,
        "skip":        False,
        "reason":      (
            f"Proportional split — "
            f"EMBASSY score {score_embassy}/10 ({e_amt/(e_amt+b_amt)*100:.0f}%), "
            f"BIRET score {score_biret}/10 ({b_amt/(e_amt+b_amt)*100:.0f}%)."
        ),
    }
