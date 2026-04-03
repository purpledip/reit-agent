"""
gdrive.py — Google Sheets backend for purchases log.

Auth flow (no JSON key required in CI):
  • GitHub Actions: google-github-actions/auth@v2 sets up Application Default
    Credentials via Workload Identity Federation → gspread picks them up.
  • Local dev: `gcloud auth application-default login` or set the
    GOOGLE_APPLICATION_CREDENTIALS env var to a local SA key file.

Requires env var GDRIVE_SHEET_ID (the long ID from the Google Sheet URL).
"""

import logging
from datetime import datetime

import gspread
import pandas as pd
from google.auth import default as google_auth_default

from config import GDRIVE_SHEET_ID

logger = logging.getLogger(__name__)

# Scopes needed to read/write Google Sheets
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column order — must match your existing sheet header
FIELDNAMES = [
    "date", "month",
    "embassy_amt", "embassy_price",
    "biret_amt", "biret_price",
    "skipped",
]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_client() -> gspread.Client:
    """Return an authorised gspread client using Application Default Credentials."""
    creds, _ = google_auth_default(scopes=_SCOPES)
    return gspread.authorize(creds)


def _get_worksheet() -> gspread.Worksheet:
    """Open the purchases sheet (first worksheet) by its ID."""
    if not GDRIVE_SHEET_ID:
        raise RuntimeError(
            "GDRIVE_SHEET_ID is not set. "
            "Set it in .env or as a GitHub Actions secret."
        )
    client = _get_client()
    spreadsheet = client.open_by_key(GDRIVE_SHEET_ID)
    return spreadsheet.sheet1


# ── Public API ────────────────────────────────────────────────────────────────

def read_purchases() -> pd.DataFrame:
    """
    Read all rows from the Google Sheet into a DataFrame.
    Returns an empty DataFrame if the sheet has no data rows.
    """
    try:
        ws = _get_worksheet()
        records = ws.get_all_records()
    except Exception as e:
        logger.error(f"Failed to read Google Sheet: {e}")
        return pd.DataFrame()

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Ensure correct dtypes (sheet may return strings)
    for col in ("embassy_amt", "embassy_price", "biret_amt", "biret_price"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df


def append_purchase(
    embassy_amt: float,
    biret_amt: float,
    embassy_price: float,
    biret_price: float,
    skipped: bool = False,
) -> None:
    """
    Append one row to the Google Sheet.
    If the sheet is empty, writes the header row first.
    """
    ws = _get_worksheet()

    # If sheet is completely empty, add header
    if not ws.get_all_values():
        ws.append_row(FIELDNAMES, value_input_option="RAW")

    row = [
        datetime.today().strftime("%Y-%m-%d"),
        datetime.today().strftime("%Y-%m"),
        round(embassy_amt, 2),
        round(embassy_price, 2),
        round(biret_amt, 2),
        round(biret_price, 2),
        "yes" if skipped else "no",
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Appended purchase row to Google Sheet: {row}")
