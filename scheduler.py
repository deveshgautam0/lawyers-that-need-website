"""
scheduler.py — Daily automation scheduler.

Two modes:
  1. Python scheduler (cross-platform): Uses the `schedule` library with a loop.
  2. Cron setup helper: Prints crontab instructions for Linux/macOS.

Run directly:  python scheduler.py          # starts the Python scheduler loop
Print cron:    python scheduler.py --cron   # prints crontab entry
One-shot:      python scheduler.py --now    # run pipeline immediately
"""

import os
import sys
import argparse
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Scheduler (Python loop) ──────────────────────────────────────────────────

SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "08:00")


def run_pipeline_once():
    """Run the pipeline in a subprocess for isolation."""
    from main import run_pipeline
    return run_pipeline()


def start_scheduler():
    """Start the schedule loop that runs the pipeline daily at SCHEDULE_TIME."""
    import schedule
    import time

    logger.info(f"Scheduler configured to run daily at {SCHEDULE_TIME}")

    schedule.every().day.at(SCHEDULE_TIME).do(run_pipeline_once)
    logger.info(f"Scheduler started. Next run at {SCHEDULE_TIME}.")

    # Run once immediately on startup (optional — comment out if unwanted)
    logger.info("Running initial pipeline...")
    run_pipeline_once()

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # Check every 30 seconds
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")
        sys.exit(0)


# ── Cron helpers ─────────────────────────────────────────────────────────────

CRONTAB_INSTRUCTION = """# ── Lead Pipeline Cron Setup ─────────────────────────────────
# Add this to your crontab (run: crontab -e)
# Runs the pipeline every day at 8:00 AM

0 8 * * * cd {pwd} && {python} scheduler.py --now >> {logfile} 2>&1

# Alternative: run every 12 hours
# 0 */12 * * * cd {pwd} && {python} scheduler.py --now >> {logfile} 2>&1

# Set your SCHEDULE_TIME env var to change the hour (24h format).
"""


def print_cron_instruction():
    """Print crontab setup instructions to stdout."""
    pwd = os.getcwd()
    python = sys.executable
    logfile = os.path.join(pwd, "cron_pipeline.log")
    print(CRONTAB_INSTRUCTION.format(pwd=pwd, python=python, logfile=logfile))
    print(f"Paste the above into your crontab (run: crontab -e)")
    print(f"Log file will be at: {logfile}")


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lead Pipeline Scheduler")
    parser.add_argument(
        "--cron",
        action="store_true",
        help="Print crontab setup instructions and exit",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run the pipeline once immediately and exit",
    )
    parser.add_argument(
        "--scheduler",
        action="store_true",
        help="Start the Python scheduler loop (default if no args)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("pipeline.log"),
        ],
    )

    if args.cron:
        print_cron_instruction()
    elif args.now:
        run_pipeline_once()
    else:
        start_scheduler()
