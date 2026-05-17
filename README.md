# Lead Generation Pipeline

A fully automated Python pipeline that scrapes Twitter/X, LinkedIn, and Reddit daily to find lawyers/law firms actively seeking a web presence. Scores and deduplicates leads, writes them to Google Sheets, and sends personalized outreach emails with a Calendly booking link.

**No official APIs. No OAuth tokens. Just web scraping.**

---

## How It Works

```
┌─────────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────────┐
│  Twitter/X  │    │   LinkedIn   │    │  Reddit  │    │              │
│  (Nitter)   │    │ (Playwright) │    │ (BS4)    │    │  Profile     │
│  8 queries  │    │  4 queries   │    │5 sub+4 Q │    │  Enrichment  │
└──────┬──────┘    └──────┬───────┘    └─────┬────┘    └──────┬───────┘
       └──────────────────┴──────────────────┘               │
                              │                               │
                              ▼                               ▼
                     ┌────────────────┐            ┌──────────────────┐
                     │  Score & Rank  │◄───────────│  Dedup DB        │
                     │  (0–100)       │            │  (SQLite)        │
                     └───────┬────────┘            └──────────────────┘
                             │
                             ▼
                     ┌────────────────┐
                     │  Top 100 Leads │
                     └───────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     ┌────────────────┐          ┌──────────────────┐
     │  Google Sheets │          │  Outreach         │
     │  (Append rows) │          │  Email / DM Draft │
     └───────┬────────┘          └────────┬─────────┘
             │                            │
             └────────────┬───────────────┘
                          ▼
                 ┌────────────────┐
                 │  Mark "Sent"   │
                 │  in Sheet + DB │
                 └────────────────┘
```

---

## File Structure

```
├── scraper.py        # Platform scrapers (Twitter, LinkedIn, Reddit)
├── scorer.py         # Lead scoring engine (0–100)
├── deduplicator.py   # SQLite deduplication database
├── sheets.py         # Google Sheets export
├── outreach.py       # Email + DM draft generation
├── main.py           # Pipeline orchestrator
├── scheduler.py      # Daily automation runner
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── README.md         # This file
```

---

## Setup Instructions

### 1. Clone & Install Dependencies

```bash
cd /path/to/Agent\ Leads
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Playwright Browsers

```bash
playwright install chromium
```

### 3. Create a Google Service Account (for Sheets)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts**
5. Create a new service account → "Editor" role
6. Create a JSON key → download and save as `service-account.json` in the project folder
7. Create a Google Sheet manually (or let the pipeline create one)
8. **Share the sheet** with the service account email (found in the JSON key, e.g., `lead-pipeline@...gserviceaccount.com`) as an Editor

### 4. Configure .env

```bash
cp .env.example .env
# Edit .env with your credentials
```

**Required variables:**

| Variable                      | Description                                      |
|-------------------------------|--------------------------------------------------|
| `SMTP_EMAIL`                  | Your Gmail / SMTP email address                  |
| `SMTP_PASSWORD`               | App password (not your regular password)         |
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | Path to service-account.json (default: ./service-account.json) |
| `GOOGLE_SHEET_NAME`           | Name of your Google Sheet                        |
| `CALENDLY_LINK`               | Your Calendly booking URL                        |

**Gmail App Password:** Go to Google Account → Security → 2-Step Verification → App passwords. Generate one for "Mail". Use that as `SMTP_PASSWORD`.

### 5. Run

**One-shot run:**
```bash
python main.py
```

**Start the scheduler (runs daily at 8 AM):**
```bash
python scheduler.py
```

**Run immediately:**
```bash
python scheduler.py --now
```

---

## Cron Setup (Alternative to Python Scheduler)

```bash
python scheduler.py --cron
```

This prints a crontab entry. Add it with:

```bash
crontab -e
# paste the line from above
```

---

## Lead Scoring Criteria

| Factor                         | Max Points |
|--------------------------------|-----------|
| Recency (today → 4–7 days)     | 30        |
| Explicit intent ("need"/"looking for") | 25  |
| Implied intent (mentions website) | 10     |
| Confirmed lawyer/law firm (bio) | 20       |
| No existing website found      | 15        |
| Has contact info in bio        | 10        |
| **Total**                      | **100**   |

---

## Google Sheet Columns

**Leads tab:**
Date Scraped | Platform | Author | Profile URL | Post URL | Post Text | Location | Email | Score | Outreach Sent? | Call Booked?

**DM Queue tab:** Same plus a DM Draft column (for leads without email).

---

## Search Queries Used

### Twitter/X (via Nitter)
- "looking for a website" (lawyer OR attorney OR "law firm")
- "need a website" (lawyer OR attorney OR "law office")
- "no website yet" (law OR legal OR attorney)
- "want a website" (lawyer OR firm)
- "doesn't have a website" attorney
- "build me a website" (lawyer OR attorney)
- "help with website" ("law firm" OR attorney)
- "recommend a web designer" (lawyer OR legal)

### LinkedIn (via Playwright)
- "looking for web developer" (lawyer OR attorney)
- "need help with website" "law firm"
- "website for my practice" (attorney OR "law office")
- "anyone know a good web designer" lawyer

### Reddit — Subreddits: r/Lawyertalk, r/LawFirm, r/SmallBusiness, r/legaladvice, r/Entrepreneur
- "website for law firm", "attorney website", "lawyer web design", "build website lawyer"

---

## Rate Limiting & Anti-Detection

- Random delays (2–8 seconds) between requests
- Rotating User-Agent strings on every request
- Nitter instance fallback (tries up to 3 mirrors)
- Playwright headless with Chrome arguments to avoid detection
- If a platform blocks the scraper, it logs the error and continues with the others

---

## Logging

All output is logged to both stdout and `pipeline.log`. Check this file for debugging.

---

## Important Notes

- **LinkedIn scraping** requires Playwright (headless browser). LinkedIn aggressively blocks automated access, so results may be limited. The scraper is best-effort.
- **Nitter instances** may go down. The scraper tries multiple mirrors and will output reduced results if none are available.
- **Email outreach** relies on SMTP. For Gmail, use an App Password (not your regular password). Enable 2FA first.
- The pipeline creates `leads.db` locally for deduplication. Never delete this file (or it will re-process old leads).
- Set `DRY_RUN=true` in `.env` to test without sending emails or writing to sheets.

---

## Troubleshooting

| Problem                          | Solution                                                     |
|----------------------------------|--------------------------------------------------------------|
| `playwright` not found            | Run `playwright install chromium`                            |
| Google Sheets auth fails          | Verify `service-account.json` path and sheet sharing         |
| SMTP authentication error        | Use an App Password, not your regular password               |
| Nitter returning 0 results        | Nitter instances may be blocked. Wait or find new instances  |
| LinkedIn returning 0 results     | LinkedIn blocks aggressively. The scraper does its best.     |
| Duplicate leads across days      | Check `leads.db` exists and isn't corrupted                  |

---

## License

MIT
