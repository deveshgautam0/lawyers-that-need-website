"""
sheets.py — Google Sheets integration for lead pipeline output.

Uses gspread + a Google Service Account to write leads to a Google Sheet.
Creates the sheet if it doesn't exist. Appends rows without overwriting prior data.
Creates a "DM Queue" tab for leads without email addresses.
"""

import os
import logging
from datetime import datetime
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Column headers for the main sheet ────────────────────────────────────────

MAIN_HEADERS = [
    "Date Scraped",
    "Platform",
    "Author",
    "Profile URL",
    "Post URL",
    "Post Text",
    "Location",
    "Email",
    "Score",
    "Outreach Sent?",
    "Call Booked?",
]

DM_QUEUE_HEADERS = [
    "Date Scraped",
    "Platform",
    "Author",
    "Profile URL",
    "Post URL",
    "Post Text",
    "DM Draft Text",
    "Outreach Sent?",
]


def _get_client() -> Optional[gspread.Client]:
    """Authenticate and return a gspread client using the service account JSON."""
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "./service-account.json")
    if not os.path.exists(creds_path):
        logger.error(f"Google service account key not found at {creds_path}")
        return None

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Google Sheets auth failed: {e}")
        return None


def _ensure_sheet(client: gspread.Client, sheet_name: str):
    """Open or create the spreadsheet. Returns the spreadsheet object."""
    try:
        return client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        logger.info(f"Sheet '{sheet_name}' not found — creating it")
        sh = client.create(sheet_name)
        # Share with the service account email (optional, for access)
        sh.sheets()[0].update_title("Leads")
        return sh
    except Exception as e:
        logger.error(f"Failed to open/create sheet: {e}")
        return None


def _ensure_worksheet(sh, title: str, headers: list):
    """Ensure a worksheet tab exists with the right headers."""
    try:
        ws = sh.worksheet(title)
        # Verify headers match; if empty, write them
        existing = ws.row_values(1) if ws.row_count else []
        if not existing:
            ws.append_row(headers)
        return ws
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.append_row(headers)
        logger.info(f"Created worksheet '{title}'")
        return ws


def append_leads(leads: List[dict], sheet_name: Optional[str] = None):
    """
    Append a list of lead dicts to the main sheet.
    Also creates/updates the DM Queue tab for leads without email.
    """
    if not leads:
        logger.info("No leads to write to sheet")
        return

    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        logger.info(f"DRY RUN: Would write {len(leads)} leads to sheet")
        return

    client = _get_client()
    if not client:
        logger.warning("Cannot write to sheets — no Google auth available")
        return

    sheet_name = sheet_name or os.getenv("GOOGLE_SHEET_NAME", "Lead Generation Pipeline")
    sh = _ensure_sheet(client, sheet_name)
    if not sh:
        return

    # 1) Main Leads tab
    ws = _ensure_worksheet(sh, "Leads", MAIN_HEADERS)
    today_str = datetime.now().strftime("%Y-%m-%d")

    rows = []
    dm_queue_rows = []
    for lead in leads:
        row = [
            today_str,
            lead.get("platform", ""),
            lead.get("author_name", lead.get("author_handle", "")),
            lead.get("profile_url", ""),
            lead.get("post_url", ""),
            lead.get("post_text", "")[:500],  # Truncate long text
            lead.get("location", ""),
            lead.get("email", ""),
            lead.get("score", 0),
            "",  # Outreach Sent? (initially blank)
            "",  # Call Booked? (initially blank)
        ]
        rows.append(row)

        # DM Queue for leads without email
        if not lead.get("email"):
            dm_row = [
                today_str,
                lead.get("platform", ""),
                lead.get("author_name", lead.get("author_handle", "")),
                lead.get("profile_url", ""),
                lead.get("post_url", ""),
                lead.get("post_text", "")[:500],
                lead.get("dm_draft", ""),
                "",
            ]
            dm_queue_rows.append(dm_row)

    # Append main rows
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        logger.info(f"Appended {len(rows)} rows to 'Leads' tab")

    # 2) DM Queue tab
    if dm_queue_rows:
        dm_ws = _ensure_worksheet(sh, "DM Queue", DM_QUEUE_HEADERS)
        dm_ws.append_rows(dm_queue_rows, value_input_option="USER_ENTERED")
        logger.info(f"Appended {len(dm_queue_rows)} rows to 'DM Queue' tab")


def mark_outreach_sent(post_url: str, sheet_name: Optional[str] = None):
    """Mark 'Outreach Sent?' as YES for a specific post URL in the sheet."""
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        return

    client = _get_client()
    if not client:
        return

    sheet_name = sheet_name or os.getenv("GOOGLE_SHEET_NAME", "Lead Generation Pipeline")
    try:
        sh = client.open(sheet_name)
        ws = sh.worksheet("Leads")
        all_records = ws.get_all_records()
        for i, record in enumerate(all_records, start=2):  # +2 because 1-indexed + header
            if record.get("Post URL", "") == post_url:
                ws.update_cell(i, 10, "YES")  # Column 10 = Outreach Sent?
                logger.info(f"Marked outreach sent for {post_url}")
                return
        logger.debug(f"Could not find {post_url} in sheet to mark outreach sent")
    except Exception as e:
        logger.warning(f"Failed to mark outreach sent in sheet: {e}")
