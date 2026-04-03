"""
budget.py — Monthly ₹5000 cap tracking
Reads and writes purchases via Google Sheets. Imported by signals.py, agent.py, bot.py, dashboard.py.
"""
from datetime import datetime
from config import MONTHLY_CAP, MIN_ORDER
from gdrive import read_purchases, append_purchase


def get_month_key(dt: datetime = None) -> str:
    return (dt or datetime.today()).strftime("%Y-%m")


def get_spent_this_month() -> dict:
    """
    Sum confirmed purchases for the current calendar month.
    Returns {"EMBASSY": float, "BIRET": float}
    """
    spent = {"EMBASSY": 0.0, "BIRET": 0.0}
    df = read_purchases()
    if df.empty:
        return spent
    month = get_month_key()
    month_data = df[df["month"] == month] if "month" in df.columns else df[0:0]
    spent["EMBASSY"] = float(month_data["embassy_amt"].sum()) if "embassy_amt" in month_data.columns else 0.0
    spent["BIRET"]   = float(month_data["biret_amt"].sum())   if "biret_amt" in month_data.columns else 0.0
    return spent


def get_remaining_budget() -> float:
    spent = get_spent_this_month()
    total_spent = spent["EMBASSY"] + spent["BIRET"]
    return max(0.0, MONTHLY_CAP - total_spent)


def log_purchase(
    embassy_amt: float,
    biret_amt: float,
    embassy_price: float,
    biret_price: float,
    skipped: bool = False,
) -> None:
    """
    Append one row to the Google Sheet.
    Always logs (including skips) so the dashboard has a full activity record.
    """
    append_purchase(
        embassy_amt=embassy_amt,
        biret_amt=biret_amt,
        embassy_price=embassy_price,
        biret_price=biret_price,
        skipped=skipped,
    )


def budget_summary() -> dict:
    """Convenience bundle used by bot.py and dashboard.py."""
    spent     = get_spent_this_month()
    remaining = get_remaining_budget()
    total     = spent["EMBASSY"] + spent["BIRET"]
    return {
        "spent_embassy": spent["EMBASSY"],
        "spent_biret":   spent["BIRET"],
        "total_spent":   total,
        "remaining":     remaining,
        "cap":           MONTHLY_CAP,
        "pct_used":      round(total / MONTHLY_CAP * 100, 1) if MONTHLY_CAP else 0,
    }
