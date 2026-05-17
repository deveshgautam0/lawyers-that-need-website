"""
main.py — Pipeline orchestrator.

Runs all modules in sequence:
  1. Scrape all platforms (Twitter, LinkedIn, Reddit)
  2. Enrich profiles
  3. Score and rank leads
  4. Deduplicate against SQLite DB
  5. Select top 100
  6. Write to Google Sheets
  7. Send outreach emails / generate DM drafts
  8. Mark seen in dedup DB
"""

import os
import sys
import logging
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ────────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log"),
    ],
)
logger = logging.getLogger("pipeline")


def run_pipeline():
    """Execute the full lead generation pipeline."""
    start_time = datetime.now()
    logger.info("=" * 70)
    logger.info(f"LEAD GENERATION PIPELINE STARTED at {start_time}")
    logger.info("=" * 70)

    # ── Module 1: Scrape ─────────────────────────────────────────────────
    from scraper import run_all_scrapers, enrich_profile
    from scorer import score_and_rank
    from deduplicator import init_db, filter_new_leads, mark_seen_batch, get_stats
    from sheets import append_leads
    from outreach import process_outreach

    # Ensure dedup DB exists
    init_db()

    all_leads = []
    scrape_results = run_all_scrapers()

    for platform, leads in scrape_results.items():
        logger.info(f"{platform}: {len(leads)} raw leads")
        all_leads.extend(leads)

    if not all_leads:
        logger.warning("No leads found from any platform. Pipeline finishing early.")
        return {"status": "no_leads", "total": 0}

    # ── Module 2: Profile enrichment ─────────────────────────────────────
    logger.info(f"Enriching profiles for {len(all_leads)} leads...")
    for i, lead in enumerate(all_leads):
        enrich_profile(lead)
        if (i + 1) % 20 == 0:
            logger.info(f"  Enriched {i+1}/{len(all_leads)} profiles")

    # ── Module 3: Score and rank ─────────────────────────────────────────
    logger.info("Scoring and ranking leads...")
    top_leads = score_and_rank(all_leads, top_n=200)  # Get extra for dedup buffer

    # ── Module 4: Deduplication ──────────────────────────────────────────
    logger.info("Deduplicating...")
    new_leads = filter_new_leads(top_leads)
    logger.info(
        f"After dedup: {len(new_leads)} new leads (from {len(top_leads)} candidates)"
    )

    # Take top 100
    final_leads = new_leads[:100]

    if not final_leads:
        logger.info("No new leads to process today.")
        return {"status": "no_new_leads", "total": 0}

    # ── Module 5: Write to Google Sheets ─────────────────────────────────
    logger.info(f"Writing {len(final_leads)} leads to Google Sheet...")
    append_leads(final_leads)

    # ── Module 6: Outreach ───────────────────────────────────────────────
    logger.info("Processing outreach...")
    outreach_summary = process_outreach(final_leads)

    # ── Module 7: Update dedup DB ────────────────────────────────────────
    mark_seen_batch(final_leads)
    stats = get_stats()
    logger.info(f"Dedup DB stats: {stats}")

    # ── Summary ──────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    summary = {
        "status": "success",
        "leads_scraped": len(all_leads),
        "top_candidates": len(top_leads),
        "new_leads": len(new_leads),
        "final_leads": len(final_leads),
        **outreach_summary,
        "elapsed_seconds": round(elapsed, 1),
    }

    logger.info("=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Duration: {elapsed:.1f}s")
    logger.info(f"  Leads scraped:   {len(all_leads)}")
    logger.info(f"  After scoring:   {len(top_leads)}")
    logger.info(f"  After dedup:     {len(new_leads)}")
    logger.info(f"  Final top 100:   {len(final_leads)}")
    logger.info(f"  Emails sent:     {outreach_summary.get('emails_sent', 0)}")
    logger.info(f"  DM drafts:       {outreach_summary.get('dm_drafts_generated', 0)}")
    logger.info(f"  Emails failed:   {outreach_summary.get('emails_failed', 0)}")
    logger.info("=" * 70)

    return summary


if __name__ == "__main__":
    run_pipeline()
