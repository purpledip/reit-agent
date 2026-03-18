"""
signals.py — Buy signal scoring and smart monthly allocation engine

Allocation philosophy:
  ₹5000 is the MONTHLY cap, not a per-day budget.
  Each day, we deploy only a FRACTION of remaining budget — sized by signal strength.
  Weak signals deploy a small slice. Strong signals deploy more. Exceptional signals
  deploy the most — but never 100%, always preserving capital for better days ahead.

Daily deployment tiers (% of remaining budget):
  Score 4–5  →  15%  (threshold met, cautious entry)
  Score 6–7  →  25%  (good signal, moderate entry)
  Score 8–9  →  40%  (strong signal, larger entry)
  Score 10   →  60%  (exceptional — RSI oversold + MACD crossover + bullish news)

The combined score of both stocks determines the day's total deployment.
Each stock's share within that total is proportional to its individual score.

Late-month safety valve:
  If fewer than 8 trading days remain in the month and > 40% of budget is
  still undeployed, the daily cap is raised by 1.5× so unspent funds don't
  roll over unused. (REITs pay monthly distributions — deploying capital
  sooner rather than later benefits from the next distribution cycle.)
"""

import pandas as pd
from datetime import datetime, date
from budget     import get_remaining_budget
from indicators import rsi, macd, sma, sentiment_score
from config     import MIN_ORDER, BUY_THRESHOLD, MONTHLY_CAP


# ── Allocation tier table ─────────────────────────────────────────────────────
# Maps combined score of qualifying stocks → fraction of remaining budget to deploy
DEPLOY_TIERS = [
    (10, 0.60),   # score 10      → deploy 60% of remaining
    (9,  0.50),   # score 9       → deploy 50%
    (8,  0.40),   # score 8       → deploy 40%
    (7,  0.30),   # score 7       → deploy 30%
    (6,  0.25),   # score 6       → deploy 25%
    (4,  0.15),   # score 4–5     → deploy 15%
]

# Hard floor/ceiling on a single day's spend, regardless of score or remaining
DAILY_MIN_DEPLOY = 500    # never deploy less than ₹500 (same as MIN_ORDER)
DAILY_MAX_DEPLOY = 3000   # never deploy more than ₹3000 in one day


def _round_down(amount: float, step: int = 10) -> int:
    """Round down to nearest ₹10 — clean, exchange-friendly order sizes."""
    return (int(amount) // step) * step


def _deploy_fraction(combined_score: int) -> float:
    """Return the fraction of remaining budget to deploy for a given combined score."""
    for threshold, fraction in DEPLOY_TIERS:
        if combined_score >= threshold:
            return fraction
    return 0.15   # fallback: minimum tier


def _trading_days_left() -> int:
    """Approximate weekdays remaining in the current calendar month."""
    today = date.today()
    # Last day of month
    if today.month == 12:
        last = date(today.year + 1, 1, 1)
    else:
        last = date(today.year, today.month + 1, 1)
    days_left = 0
    d = today
    while d < last:
        if d.weekday() < 5:   # Mon–Fri
            days_left += 1
        d = date(d.year, d.month, d.day + 1) if d.day < 28 else (
            date(d.year, d.month + 1, 1) if d.month < 12 else date(d.year + 1, 1, 1)
        )
    return max(1, days_left)


def _late_month_multiplier(remaining: float) -> float:
    """
    If we're late in the month and have lots of budget left, deploy faster.
    Returns a multiplier applied on top of the normal fraction.
    """
    days_left     = _trading_days_left()
    pct_remaining = remaining / MONTHLY_CAP

    if days_left <= 5 and pct_remaining > 0.50:
        return 2.0   # last week, more than half budget left → deploy fast
    if days_left <= 8 and pct_remaining > 0.40:
        return 1.5   # 8 days left, 40%+ undeployed → deploy a bit faster
    return 1.0


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
        float(macd_line.iloc[-1])  > float(signal_line.iloc[-1]) and
        float(macd_line.iloc[-2])  < float(signal_line.iloc[-2])
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
    Smart monthly allocation engine.

    Steps:
      1. Check hard blockers (cap exhausted, below minimum, no signal)
      2. Compute today's deployable amount based on signal strength
         and how much of the month is left
      3. Split that deployable amount between qualifying stocks
         proportionally by their individual scores
      4. Apply all existing edge case guards (sub-minimum splits, rounding)

    Returns:
      {
        "embassy_amt":      int,    # ₹ to buy EMBASSY today  (0 = skip)
        "biret_amt":        int,    # ₹ to buy BIRET today    (0 = skip)
        "skip":             bool,
        "reason":           str,    # shown in Telegram message
        "deploy_pct":       float,  # % of remaining deployed today
        "days_left":        int,    # trading days left this month
      }
    """
    remaining = get_remaining_budget()

    base = {
        "embassy_amt": 0,
        "biret_amt":   0,
        "skip":        True,
        "deploy_pct":  0.0,
        "days_left":   _trading_days_left(),
    }

    # ── Hard blockers ─────────────────────────────────────────────────────────

    if remaining <= 0:
        return {**base, "reason": f"Monthly ₹{MONTHLY_CAP:,} cap fully used. No more buys this month."}

    if remaining < MIN_ORDER:
        return {**base, "reason": (
            f"₹{remaining:.0f} left — below minimum order ₹{MIN_ORDER}. "
            "Rolls over to next month."
        )}

    e_ok = score_embassy >= BUY_THRESHOLD
    b_ok = score_biret   >= BUY_THRESHOLD

    if not e_ok and not b_ok:
        return {**base, "reason": (
            f"No buy signal. EMBASSY {score_embassy}/10, BIRET {score_biret}/10 "
            f"(need ≥ {BUY_THRESHOLD}). Preserving capital."
        )}

    # ── Compute today's deployable amount ─────────────────────────────────────

    # Use the higher of the two qualifying scores to determine aggression
    qualifying_scores = [s for s, ok in [(score_embassy, e_ok), (score_biret, b_ok)] if ok]
    best_score        = max(qualifying_scores)
    combined_score    = score_embassy + score_biret if (e_ok and b_ok) else best_score

    fraction    = _deploy_fraction(best_score)
    multiplier  = _late_month_multiplier(remaining)
    raw_deploy  = remaining * fraction * multiplier

    # Clamp to daily floor / ceiling
    deploy_amt  = max(DAILY_MIN_DEPLOY, min(DAILY_MAX_DEPLOY, raw_deploy))
    deploy_amt  = min(deploy_amt, remaining)              # can't exceed what's left
    deploy_amt  = _round_down(deploy_amt)

    if deploy_amt < MIN_ORDER:
        return {**base, "reason": (
            f"Computed deployment ₹{deploy_amt} below minimum ₹{MIN_ORDER}. "
            "Waiting for a stronger signal."
        )}

    deploy_pct = round(deploy_amt / remaining * 100, 1)

    # ── Split deploy_amt between qualifying stocks ────────────────────────────

    if e_ok and not b_ok:
        e_amt, b_amt = deploy_amt, 0
        reason = (
            f"EMBASSY {score_embassy}/10 qualifies · BIRET {score_biret}/10 too low. "
            f"Deploying {deploy_pct}% of remaining (₹{deploy_amt:,}) → EMBASSY."
        )

    elif b_ok and not e_ok:
        e_amt, b_amt = 0, deploy_amt
        reason = (
            f"BIRET {score_biret}/10 qualifies · EMBASSY {score_embassy}/10 too low. "
            f"Deploying {deploy_pct}% of remaining (₹{deploy_amt:,}) → BIRET."
        )

    else:
        # Both qualify — split proportionally by score
        total_score = score_embassy + score_biret
        raw_e = (score_embassy / total_score) * deploy_amt
        raw_b = deploy_amt - raw_e
        e_amt = _round_down(raw_e)
        b_amt = _round_down(raw_b)

        # Sub-minimum split guards
        if e_amt < MIN_ORDER and b_amt < MIN_ORDER:
            # Deploy all to the stronger stock
            if score_embassy >= score_biret:
                e_amt, b_amt = deploy_amt, 0
                split_note = "split too small — all → EMBASSY"
            else:
                e_amt, b_amt = 0, deploy_amt
                split_note = "split too small — all → BIRET"
        elif e_amt < MIN_ORDER:
            b_amt = deploy_amt
            e_amt = 0
            split_note = f"EMBASSY share ₹{e_amt} < min — redirected to BIRET"
        elif b_amt < MIN_ORDER:
            e_amt = deploy_amt
            b_amt = 0
            split_note = f"BIRET share ₹{b_amt} < min — redirected to EMBASSY"
        else:
            split_note = (
                f"EMBASSY {e_amt/(e_amt+b_amt)*100:.0f}% / "
                f"BIRET {b_amt/(e_amt+b_amt)*100:.0f}%"
            )

        reason = (
            f"Both qualify (EMBASSY {score_embassy}/10, BIRET {score_biret}/10). "
            f"Deploying {deploy_pct}% of remaining (₹{deploy_amt:,}). "
            f"{split_note}."
        )

    # ── Final rounding safety ─────────────────────────────────────────────────
    if e_amt == 0 and b_amt == 0:
        winner = "EMBASSY" if score_embassy >= score_biret else "BIRET"
        e_amt  = deploy_amt if winner == "EMBASSY" else 0
        b_amt  = deploy_amt if winner == "BIRET"   else 0
        reason += f" Rounding fallback → all to {winner}."

    return {
        "embassy_amt": e_amt,
        "biret_amt":   b_amt,
        "skip":        False,
        "reason":      reason,
        "deploy_pct":  deploy_pct,
        "days_left":   _trading_days_left(),
    }