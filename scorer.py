"""
scorer.py — Lead scoring engine (score 0–100).

Evaluates each lead on:
  - Recency: posted today=30pts, 1-3 days=20pts, 4-7 days=10pts
  - Explicit intent: direct "looking for"/"need"=25pts, implied=10pts
  - Confirmed lawyer/law firm in bio: +20pts
  - No existing website found: +15pts
  - Contact info in bio: +10pts
"""

import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Intent keywords — explicit vs. implied
EXPLICIT_INTENT_PATTERNS = [
    r"\blooking for\b.*\b(websit|web\s*design|web\s*dev|web\s*presence|site)\b",
    r"\bneed\b.*\b(websit|web\s*design|web\s*dev|site)\b",
    r"\bwant\b.*\b(websit|web\s*dev|web\s*design|site)\b",
    r"\bbuild\b.*\b(websit|site)\b",
    r"\bhelp\b.*\b(with\s*websit|with\s*site)\b",
    r"\brecommend\b.*\bweb\b",
    r"\bdoesn'?t have a website\b",
    r"\bno website yet\b",
    r"\banyone know\b.*\b(web\s*design|web\s*dev|websit)\b",
]

IMPLIED_INTENT_PATTERNS = [
    r"\bwebsit\b",
    r"\bweb\s*(design|dev|presence|site|developer|designer)\b",
    r"\bonline presence\b",
    r"\bprofessional website\b",
]

LAWYER_KEYWORDS = [
    r"\blawyer\b", r"\battorney\b", r"\blaw\b", r"\blegal\b",
    r"\blaw\s*firm\b", r"\blaw\s*office\b", r"\bpractice\b",
    r"\besq\b", r"\besquire\b", r"\bbarrister\b", r"\bsolicitor\b",
    r"\bjuris\b", r"\bll\.?b\b", r"\bj\.?d\b",
]


def score_lead(lead: dict) -> int:
    """
    Score a single lead dict. Mutates lead['score'] in place and returns it.

    Expected lead keys: post_text, author_bio, post_date, existing_website, email, platform, author_handle
    """
    score = 0
    post_text = (lead.get("post_text") or "").lower()
    author_bio = (lead.get("author_bio") or "").lower()
    post_date = lead.get("post_date")

    # 1) Recency (up to 30 pts)
    score += _score_recency(post_date)

    # 2) Intent (up to 25 pts)
    score += _score_intent(post_text)

    # 3) Confirmed lawyer (up to 20 pts)
    combined_text = f"{post_text} {author_bio}"
    if _is_lawyer(combined_text):
        score += 20

    # 4) No existing website (up to 15 pts)
    if not lead.get("existing_website", True):
        score += 15

    # 5) Has contact info (up to 10 pts)
    if lead.get("email"):
        score += 10

    score = min(score, 100)
    lead["score"] = score
    return score


def _score_recency(post_date):
    """Score based on how recent the post is."""
    if not post_date:
        return 0
    now = datetime.now()
    if isinstance(post_date, str):
        try:
            post_date = datetime.fromisoformat(post_date)
        except (ValueError, TypeError):
            return 0
    days_ago = (now - post_date).days
    if days_ago < 1:
        return 30
    elif days_ago <= 3:
        return 20
    elif days_ago <= 7:
        return 10
    return 0


def _score_intent(text: str) -> int:
    """Score 25 for explicit intent, 10 for implied, 0 for none."""
    for pattern in EXPLICIT_INTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 25
    for pattern in IMPLIED_INTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 10
    return 0


def _is_lawyer(text: str) -> bool:
    """Check if text indicates the author is a lawyer/law firm."""
    for pattern in LAWYER_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def score_and_rank(leads: list, top_n: int = 100) -> list:
    """Score all leads, sort descending, return top N."""
    for lead in leads:
        score_lead(lead)
    ranked = sorted(leads, key=lambda x: x.get("score", 0), reverse=True)
    logger.info(
        f"Scored {len(ranked)} leads — top score: {ranked[0]['score'] if ranked else 'N/A'}"
    )
    return ranked[:top_n]
