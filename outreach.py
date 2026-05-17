"""
outreach.py — Automated email outreach and DM draft generation.

Uses smtplib to send personalized emails to leads with an email address.
Generates DM drafts (for manual sending) for leads without email.
All messages reference the specific post and include a Calendly link.
"""

import os
import re
import logging
import random
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _get_smtp_config() -> dict:
    """Read SMTP config from environment."""
    return {
        "server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "email": os.getenv("SMTP_EMAIL", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
    }


def _get_calendly_link() -> str:
    """Get the Calendly booking link from env."""
    return os.getenv("CALENDLY_LINK", "https://calendly.com/your-link/30min")


def _truncate_name(name: str, max_len: int = 30) -> str:
    """Safely truncate a name for the subject line."""
    name = re.sub(r"[\[\]\(\)\{\}]", "", name).strip()
    if len(name) > max_len:
        name = name[: max_len - 3] + "..."
    return name


def generate_subject_line(lead: dict) -> str:
    """Generate a personalized email subject line."""
    name = _truncate_name(lead.get("author_name", "") or lead.get("author_handle", ""))
    return f"Quick question about your website — {name}"


def generate_email_body(lead: dict) -> str:
    """Generate a short, personal outreach email body."""
    platform = lead.get("platform", "a forum")
    author_name = lead.get("author_name", "") or lead.get("author_handle", "there")
    first_name = author_name.split()[0] if author_name.split() else "there"
    calendly = _get_calendly_link()

    # Extract a short excerpt from their post to reference
    post_text = lead.get("post_text", "")
    excerpt = post_text[:150].rsplit(" ", 1)[0] + "..." if len(post_text) > 150 else post_text

    body = (
        f"Hi {first_name},\n\n"
        f"I came across your post on {platform} about needing a website "
        f"(\"{excerpt}\")."
        f"\n\n"
        f"I help lawyers and law firms build modern, professional websites that "
        f"actually generate leads. Would you be open to a quick 15-minute call "
        f"to see if I can help?\n\n"
        f"Here's my calendar link if you'd like to book some time:\n{calendly}\n\n"
        f"Best,\n[Your Name]"
    )
    return body


def generate_dm_draft(lead: dict) -> str:
    """Generate a DM draft for platforms where we can email directly."""
    platform = lead.get("platform", "a forum")
    author_name = lead.get("author_name", "") or lead.get("author_handle", "there")
    first_name = author_name.split()[0] if author_name.split() else "there"
    calendly = _get_calendly_link()

    post_text = lead.get("post_text", "")
    excerpt = post_text[:120].rsplit(" ", 1)[0] + "..." if len(post_text) > 120 else post_text

    dm = (
        f"Hi {first_name}! Saw your post on {platform} about needing a website "
        f"(\"{excerpt}\"). I build websites for legal professionals and thought "
        f"I'd reach out. Happy to chat if you're open to it — "
        f"{calendly}"
    )
    return dm


def send_email(lead: dict) -> bool:
    """
    Send a personalized outreach email to a lead.
    Returns True if sent successfully, False otherwise.
    """
    email_addr = lead.get("email", "").strip()
    if not email_addr:
        logger.debug(f"No email for {lead.get('author_handle', 'unknown')} — skipping")
        return False

    # Validate email format
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email_addr):
        logger.warning(f"Invalid email format: {email_addr}")
        return False

    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        logger.info(f"DRY RUN: Would send email to {email_addr}")
        lead["outreach_sent"] = True
        return True

    smtp = _get_smtp_config()
    if not smtp["email"] or not smtp["password"]:
        logger.warning("SMTP not configured — set SMTP_EMAIL and SMTP_PASSWORD in .env")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp["email"]
        msg["To"] = email_addr
        msg["Subject"] = generate_subject_line(lead)

        body = generate_email_body(lead)
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp["server"], smtp["port"]) as server:
            server.starttls()
            server.login(smtp["email"], smtp["password"])
            server.send_message(msg)

        logger.info(f"Email sent to {email_addr}")
        lead["outreach_sent"] = True
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP auth failed. Check your SMTP_EMAIL and SMTP_PASSWORD.")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending to {email_addr}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending to {email_addr}: {e}")
        return False


def process_outreach(leads: List[dict]) -> dict:
    """
    Process outreach for all leads.
    - Leads with email: attempt to send email
    - Leads without email: generate DM draft

    Returns a summary dict with counts.
    """
    sent = 0
    failed = 0
    dm_drafts = 0

    for lead in leads:
        if lead.get("email"):
            if send_email(lead):
                sent += 1
            else:
                failed += 1
        else:
            # Generate DM draft and attach it for the sheets export
            lead["dm_draft"] = generate_dm_draft(lead)
            dm_drafts += 1

        # Small delay between sends to avoid rate limiting
        if lead.get("email"):
            time.sleep(random.uniform(2, 5))

    summary = {
        "emails_sent": sent,
        "emails_failed": failed,
        "dm_drafts_generated": dm_drafts,
        "total_processed": len(leads),
    }
    logger.info(f"Outreach summary: {summary}")
    return summary
