"""
budget.py — Monthly ₹5000 cap tracking
Reads and writes purchases.csv. Imported by signals.py, agent.py, bot.py, dashboard.py.
"""
import csv
import os
from datetime import datetime
from config import LOG_FILE, MONTHLY_CAP, MIN_ORDER


def get_month_key(dt: datetime = None) -> str:
    return (dt or datetime.today()).strftime("%Y-%m")


def get_spent_this_month() -> dict:
    """
    Sum confirmed purchases for the current calendar month.
    Returns {"EMBASSY": float, "BIRET": float}
    """
    spent = {"EMBASSY": 0.0, "BIRET": 0.0}
    if not os.path.exists(LOG_FILE):
        return spent
    month = get_month_key()
    with open(LOG_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("month") == month:
                spent["EMBASSY"] += float(row.get("embassy_amt", 0))
                spent["BIRET"]   += float(row.get("biret_amt", 0))
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
    Append one row to purchases.csv.
    Always logs (including skips) so the dashboard has a full activity record.
    """
    file_exists = os.path.exists(LOG_FILE)
    fieldnames  = [
        "date", "month",
        "embassy_amt", "embassy_price",
        "biret_amt",   "biret_price",
        "skipped",
    ]
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "date":          datetime.today().strftime("%Y-%m-%d"),
            "month":         get_month_key(),
            "embassy_amt":   round(embassy_amt, 2),
            "embassy_price": round(embassy_price, 2),
            "biret_amt":     round(biret_amt, 2),
            "biret_price":   round(biret_price, 2),
            "skipped":       "yes" if skipped else "no",
        })


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
