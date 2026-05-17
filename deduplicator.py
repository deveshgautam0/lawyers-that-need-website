"""
deduplicator.py — SQLite-backed deduplication database.

Maintains a persistent store of all scraped post URLs and author handles.
Provides check/insert operations so leads aren't re-processed across days.
"""

import sqlite3
import logging
from datetime import datetime
from typing import List, Tuple

logger = logging.getLogger(__name__)

DB_PATH = "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_url TEXT UNIQUE NOT NULL,
    author_handle TEXT NOT NULL,
    platform TEXT NOT NULL,
    first_seen DATE NOT NULL,
    score INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_post_url ON seen_posts(post_url);
CREATE INDEX IF NOT EXISTS idx_author ON seen_posts(author_handle);
"""


def init_db(db_path: str = DB_PATH):
    """Initialize the SQLite database and create tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    logger.info(f"Deduplication DB initialized at {db_path}")


def is_duplicate(post_url: str, author_handle: str, db_path: str = DB_PATH) -> bool:
    """Check if a post URL or author handle already exists in the DB."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM seen_posts WHERE post_url = ? OR author_handle = ?",
        (post_url, author_handle),
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def mark_seen(post_url: str, author_handle: str, platform: str, score: int, db_path: str = DB_PATH):
    """Record a lead as seen so future runs skip it."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO seen_posts (post_url, author_handle, platform, first_seen, score)
               VALUES (?, ?, ?, ?, ?)""",
            (post_url, author_handle, platform, datetime.now().strftime("%Y-%m-%d"), score),
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.warning(f"DB insert failed for {post_url}: {e}")
    finally:
        conn.close()


def mark_seen_batch(leads: List[dict], db_path: str = DB_PATH):
    """Record multiple leads in one transaction."""
    conn = sqlite3.connect(db_path)
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = [
            (l["post_url"], l["author_handle"], l["platform"], today, l.get("score", 0))
            for l in leads
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO seen_posts (post_url, author_handle, platform, first_seen, score)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        logger.info(f"Marked {len(rows)} leads as seen in dedup DB")
    except sqlite3.Error as e:
        logger.warning(f"Batch DB insert failed: {e}")
    finally:
        conn.close()


def filter_new_leads(leads: List[dict], db_path: str = DB_PATH) -> List[dict]:
    """Filter out leads already in the DB. Returns only unseen leads."""
    new_leads = []
    skipped = 0
    for lead in leads:
        if is_duplicate(lead["post_url"], lead["author_handle"], db_path):
            skipped += 1
        else:
            new_leads.append(lead)
    if skipped:
        logger.info(f"Dedup skipped {skipped} already-seen leads")
    return new_leads


def get_stats(db_path: str = DB_PATH) -> dict:
    """Return summary stats about the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM seen_posts")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT author_handle) FROM seen_posts")
    unique_authors = cursor.fetchone()[0]
    cursor.execute(
        "SELECT platform, COUNT(*) FROM seen_posts GROUP BY platform ORDER BY COUNT(*) DESC"
    )
    by_platform = dict(cursor.fetchall())
    conn.close()
    return {"total_leads": total, "unique_authors": unique_authors, "by_platform": by_platform}
