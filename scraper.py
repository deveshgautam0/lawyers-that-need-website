"""
scraper.py — Multi-platform web scraper for lead generation.

Platforms:
  - Twitter/X via nitter.net (read-only, no login required)
  - LinkedIn via Playwright (headless browser, public search)
  - Reddit via requests + BeautifulSoup on old.reddit.com

All scrapers return a list of dicts with a consistent schema.
No official APIs or OAuth tokens used.
"""

import re
import time
import random
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── User-Agent rotation ──────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _random_delay(min_s: float = 3.0, max_s: float = 8.0):
    """Sleep for a random interval to avoid rate limiting."""
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)


def _random_headers() -> dict:
    """Return a headers dict with a random User-Agent."""
    return {**HEADERS, "User-Agent": random.choice(USER_AGENTS)}


def _safe_get(soup, selector, attr=None, default=""):
    """Safely extract text or attribute from a CSS selector."""
    try:
        elems = soup.select(selector)
        if not elems:
            return default
        if attr:
            val = elems[0].get(attr, default)
        else:
            val = elems[0].get_text(strip=True)
        return val or default
    except Exception:
        return default


def _parse_date_relative(text: str) -> Optional[datetime]:
    """Parse relative date strings like '2h ago', '3 days ago', 'Jan 5'."""
    if not text:
        return None
    text = text.strip().lower()
    now = datetime.now()

    # "just now", "now"
    if text in ("now", "just now"):
        return now

    # "Xm ago", "Xh ago", "Xd ago"
    m = re.match(r"(\d+)\s*(m|min|h|d|day|days)\s*ago", text)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        if unit in ("m", "min"):
            return now - timedelta(minutes=num)
        elif unit in ("h",):
            return now - timedelta(hours=num)
        elif unit in ("d", "day", "days"):
            return now - timedelta(days=num)

    # "Jan 5", "January 5, 2024"
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d", "%B %d", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(year=now.year if dt.year == 1900 else dt.year)
        except ValueError:
            continue
    return None


# ── Nitter (Twitter/X) Scraper ───────────────────────────────────────────────

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.unixfox.eu",
    "https://nitter.lqdev.org",
]

TWITTER_QUERIES = [
    '"looking for a website" (lawyer OR attorney OR "law firm")',
    '"need a website" (lawyer OR attorney OR "law office")',
    '"no website yet" (law OR legal OR attorney)',
    '"want a website" (lawyer OR firm)',
    '"doesn\'t have a website" attorney',
    '"build me a website" (lawyer OR attorney)',
    '"help with website" ("law firm" OR attorney)',
    '"recommend a web designer" (lawyer OR legal)',
]


def _try_nitter_instance(query: str, instance: str) -> list:
    """Try scraping a single nitter instance for a query."""
    url = f"{instance}/search?f=tweets&q={quote_plus(query)}"
    try:
        resp = requests.get(url, headers=_random_headers(), timeout=30)
        if resp.status_code != 200:
            logger.debug(f"Nitter {instance} returned {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        tweets = []
        for article in soup.select("div.timeline-item"):
            try:
                post_text_el = article.select_one("div.tweet-content")
                if not post_text_el:
                    continue
                post_text = post_text_el.get_text(strip=True)

                author_el = article.select_one("a.username")
                author_handle = author_el.get_text(strip=True) if author_el else ""

                name_el = article.select_one("a.fullname")
                author_name = name_el.get_text(strip=True) if name_el else ""

                date_el = article.select_one("span.tweet-date a")
                date_text = date_el.get("title", "") if date_el else ""
                post_date = _parse_date_relative(date_text) or _parse_date_relative(
                    date_el.get_text(strip=True) if date_el else ""
                )

                permalink_el = article.select_one("a.tweet-link")
                post_url = ""
                if permalink_el:
                    href = permalink_el.get("href", "")
                    post_url = f"{instance}{href}" if href.startswith("/") else href

                tweets.append(
                    {
                        "platform": "Twitter",
                        "post_url": post_url,
                        "author_handle": author_handle,
                        "author_name": author_name,
                        "post_text": post_text,
                        "post_date": post_date.isoformat() if post_date else "",
                        "profile_url": f"{instance}/{author_handle}" if author_handle else "",
                        "author_bio": "",
                        "location": "",
                        "email": "",
                        "existing_website": False,
                        "followers": 0,
                    }
                )
            except Exception as e:
                logger.debug(f"Nitter tweet parse error: {e}")
                continue
        return tweets
    except requests.RequestException as e:
        logger.debug(f"Nitter {instance} failed: {e}")
        return []


def scrape_twitter(max_results: int = 150) -> list:
    """
    Scrape Twitter/X via multiple nitter.net instances.
    Falls through instances until we get results or exhaust them.
    """
    all_tweets = []
    random.shuffle(NITTER_INSTANCES)

    for instance in NITTER_INSTANCES[:3]:  # Try up to 3 instances
        for query in TWITTER_QUERIES:
            try:
                tweets = _try_nitter_instance(query, instance)
                all_tweets.extend(tweets)
                logger.info(
                    f"Nitter {instance} | {query[:50]}... → {len(tweets)} results"
                )
                if len(all_tweets) >= max_results:
                    break
                _random_delay(2, 6)
            except Exception as e:
                logger.warning(f"Nitter scrape error on {instance}: {e}")
                continue
        if all_tweets:
            break

    # Deduplicate by post URL within this batch
    seen_urls = set()
    unique = []
    for t in all_tweets:
        if t["post_url"] and t["post_url"] not in seen_urls:
            seen_urls.add(t["post_url"])
            unique.append(t)

    logger.info(f"Twitter scraper: {len(unique)} unique results")
    return unique[:max_results]


# ── LinkedIn Scraper ─────────────────────────────────────────────────────────

LINKEDIN_QUERIES = [
    '"looking for web developer" (lawyer OR attorney)',
    '"need help with website" "law firm"',
    '"website for my practice" (attorney OR "law office")',
    '"anyone know a good web designer" lawyer',
]


def scrape_linkedin(max_results: int = 100) -> list:
    """
    Scrape LinkedIn public posts using Playwright headless browser.
    Searches via linkedin.com/search and extracts public posts.
    """
    leads = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright not installed. Run: pip install playwright && playwright install")
        return leads

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        for query in LINKEDIN_QUERIES:
            try:
                search_url = f"https://www.linkedin.com/search/results/content/?keywords={quote_plus(query)}"
                page.goto(search_url, wait_until="domcontentloaded")
                _random_delay(4, 8)

                # Scroll to load more
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    _random_delay(2, 4)

                # Parse posts from the search results
                posts = page.query_selector_all("div.feed-shared-update-v2__description")
                authors = page.query_selector_all("span.update-components-actor__name")
                dates = page.query_selector_all("span.update-components-actor__sub-description")

                for i, post_el in enumerate(posts):
                    try:
                        post_text = post_el.inner_text().strip()
                        if not post_text:
                            continue

                        author_name = authors[i].inner_text().strip() if i < len(authors) else ""
                        date_text = dates[i].inner_text().strip() if i < len(dates) else ""
                        post_date = _parse_date_relative(date_text)

                        # Build a pseudo-handle from the name
                        handle = author_name.lower().replace(" ", "-").replace(".", "")
                        # Hash the URL for dedup
                        post_url = f"linkedin://post/{hash(post_text[:100])}"

                        leads.append(
                            {
                                "platform": "LinkedIn",
                                "post_url": post_url,
                                "author_handle": handle,
                                "author_name": author_name,
                                "post_text": post_text,
                                "post_date": post_date.isoformat() if post_date else "",
                                "profile_url": "",
                                "author_bio": "",
                                "location": "",
                                "email": "",
                                "existing_website": False,
                                "followers": 0,
                            }
                        )
                    except Exception:
                        continue

                logger.info(f"LinkedIn | {query[:50]}... → scraped page")
                _random_delay(3, 7)

            except Exception as e:
                logger.warning(f"LinkedIn scrape error for '{query[:40]}': {e}")
                page.goto("about:blank")
                continue

        browser.close()

    # Dedup
    seen = set()
    unique = []
    for l in leads:
        if l["post_url"] and l["post_url"] not in seen:
            seen.add(l["post_url"])
            unique.append(l)

    logger.info(f"LinkedIn scraper: {len(unique)} unique results")
    return unique[:max_results]


# ── Reddit Scraper ───────────────────────────────────────────────────────────

REDDIT_SUBREDDITS = [
    "Lawyertalk",
    "LawFirm",
    "SmallBusiness",
    "legaladvice",
    "Entrepreneur",
]

REDDIT_QUERIES = [
    '"website for law firm"',
    '"attorney website"',
    '"lawyer web design"',
    '"build website lawyer"',
    '"law firm website"',
    '"website for my law"',
    '"need a website" law',
]

REDDIT_AGE_FILTER = timedelta(days=7)


def _extract_email(text: str) -> str:
    """Extract email from text using regex."""
    match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else ""


def scrape_reddit(max_results: int = 200) -> list:
    """Scrape Reddit via old.reddit.com using requests + BeautifulSoup."""
    posts = []

    for subreddit in REDDIT_SUBREDDITS:
        for query in REDDIT_QUERIES:
            url = (
                f"https://old.reddit.com/r/{subreddit}/search"
                f"?q={quote_plus(query)}"
                f"&restrict_sr=on&sort=new&t=week"
            )
            try:
                resp = requests.get(url, headers=_random_headers(), timeout=30)
                if resp.status_code != 200:
                    logger.debug(f"Reddit r/{subreddit} returned {resp.status_code}")
                    _random_delay(2, 5)
                    continue

                soup = BeautifulSoup(resp.text, "lxml")
                for entry in soup.select("div.thing"):
                    try:
                        title_el = entry.select_one("a.title")
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        post_url = title_el.get("href", "")

                        # Convert relative URLs
                        if post_url.startswith("/r/"):
                            post_url = f"https://old.reddit.com{post_url}"

                        # Author
                        author_el = entry.select_one("a.author")
                        author_handle = author_el.get_text(strip=True) if author_el else ""

                        # Date
                        date_el = entry.select_one("time")
                        date_text = date_el.get("title", "") if date_el else ""
                        post_date = None
                        if date_text:
                            try:
                                post_date = datetime.fromisoformat(date_text.replace(" ", "T"))
                            except ValueError:
                                post_date = _parse_date_relative(date_text)

                        # Score
                        score_el = entry.select_one("div.score.likes")
                        score_text = score_el.get_text(strip=True) if score_el else "0"

                        # Self-text (expand preview)
                        selftext_el = entry.select_one("div.usertext-body")
                        selftext = selftext_el.get_text(strip=True) if selftext_el else ""

                        # Description (author flair or subreddit flair)
                        flair_el = entry.select_one("span.linkflairlabel")
                        flair = flair_el.get_text(strip=True) if flair_el else ""

                        # Get actual post content (for self posts, visit the post page)
                        post_text = f"{title}. {selftext}".strip()
                        if not post_text:
                            continue

                        # Extract email from post text
                        email = _extract_email(post_text)

                        # Filter: discard posts older than 7 days
                        if post_date and (datetime.now() - post_date) > REDDIT_AGE_FILTER:
                            continue

                        # Profile URL
                        profile_url = (
                            f"https://old.reddit.com/user/{author_handle}/"
                            if author_handle and author_handle != "[deleted]"
                            else ""
                        )

                        posts.append(
                            {
                                "platform": "Reddit",
                                "post_url": post_url,
                                "author_handle": author_handle,
                                "author_name": author_handle,
                                "post_text": post_text,
                                "post_date": post_date.isoformat() if post_date else "",
                                "profile_url": profile_url,
                                "author_bio": flair,
                                "location": "",
                                "email": email,
                                "existing_website": False,
                                "followers": 0,
                            }
                        )
                    except Exception as e:
                        logger.debug(f"Reddit post parse error: {e}")
                        continue

                logger.info(f"Reddit r/{subreddit} | {query[:40]} → parsed entries")
                _random_delay(2, 6)

            except requests.RequestException as e:
                logger.warning(f"Reddit r/{subreddit} scrape error: {e}")
                continue

    # For Reddit, also scrape hot/new posts in these subreddits as fallback
    for subreddit in REDDIT_SUBREDDITS:
        url = f"https://old.reddit.com/r/{subreddit}/new/"
        try:
            resp = requests.get(url, headers=_random_headers(), timeout=30)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for entry in soup.select("div.thing"):
                try:
                    title_el = entry.select_one("a.title")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)

                    # Check if title contains any website-related keywords
                    if not any(
                        kw in title.lower()
                        for kw in [
                            "website", "web", "site", "online presence",
                            "build", "design", "developer", "need",
                            "looking for", "help with",
                        ]
                    ):
                        continue

                    post_url = title_el.get("href", "")
                    if post_url.startswith("/r/"):
                        post_url = f"https://old.reddit.com{post_url}"

                    author_el = entry.select_one("a.author")
                    author_handle = author_el.get_text(strip=True) if author_el else ""

                    date_el = entry.select_one("time")
                    date_text = date_el.get("title", "") if date_el else ""
                    post_date = None
                    if date_text:
                        try:
                            post_date = datetime.fromisoformat(date_text.replace(" ", "T"))
                        except ValueError:
                            pass

                    selftext_el = entry.select_one("div.usertext-body")
                    selftext = selftext_el.get_text(strip=True) if selftext_el else ""
                    post_text = f"{title}. {selftext}".strip()

                    if (post_date and (datetime.now() - post_date) > REDDIT_AGE_FILTER) or not post_text:
                        continue

                    email = _extract_email(post_text)
                    profile_url = (
                        f"https://old.reddit.com/user/{author_handle}/"
                        if author_handle and author_handle != "[deleted]"
                        else ""
                    )

                    posts.append(
                        {
                            "platform": "Reddit",
                            "post_url": post_url,
                            "author_handle": author_handle,
                            "author_name": author_handle,
                            "post_text": post_text,
                            "post_date": post_date.isoformat() if post_date else "",
                            "profile_url": profile_url,
                            "author_bio": "",
                            "location": "",
                            "email": email,
                            "existing_website": False,
                            "followers": 0,
                        }
                    )
                except Exception:
                    continue
            _random_delay(1, 3)
        except requests.RequestException:
            continue

    # Dedup
    seen_urls = set()
    unique = []
    for p in posts:
        if p["post_url"] and p["post_url"] not in seen_urls:
            seen_urls.add(p["post_url"])
            unique.append(p)

    logger.info(f"Reddit scraper: {len(unique)} unique posts")
    return unique[:max_results]


# ── Profile Enrichment (optional, per-lead) ─────────────────────────────────

def enrich_profile(lead: dict):
    """
    Attempt to enrich a lead by visiting their profile page.
    For Twitter handles via Nitter, for Reddit via old.reddit.com.
    """
    if lead["platform"] == "Twitter" and lead["profile_url"]:
        try:
            resp = requests.get(lead["profile_url"], headers=_random_headers(), timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                bio_el = soup.select_one("div.profile-bio")
                if bio_el:
                    lead["author_bio"] = bio_el.get_text(strip=True)
                loc_el = soup.select_one("span.profile-location")
                if loc_el:
                    lead["location"] = loc_el.get_text(strip=True)
                # Check for website link
                website_el = soup.select_one("a.profile-website")
                lead["existing_website"] = website_el is not None
                # Extract email from bio
                if not lead["email"]:
                    lead["email"] = _extract_email(lead["author_bio"])
        except Exception as e:
            logger.debug(f"Profile enrichment failed for {lead['author_handle']}: {e}")

    elif lead["platform"] == "Reddit" and lead["profile_url"]:
        try:
            resp = requests.get(lead["profile_url"], headers=_random_headers(), timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                bio_el = soup.select_one("div.profile-bio")
                if bio_el:
                    lead["author_bio"] = bio_el.get_text(strip=True)
                # Check for links in their posts
                links = soup.select("a[href]")
                for link in links:
                    href = link.get("href", "")
                    if href.startswith("http") and "reddit.com" not in href:
                        lead["existing_website"] = True
                        break
                if not lead["email"]:
                    lead["email"] = _extract_email(lead["author_bio"])
        except Exception as e:
            logger.debug(f"Reddit profile enrichment failed: {e}")


# ── Unified Scraper ──────────────────────────────────────────────────────────

def run_all_scrapers() -> dict:
    """Run all platform scrapers and return results keyed by platform."""
    results = {}

    logger.info("=" * 60)
    logger.info("Starting Twitter/X scrape...")
    try:
        results["twitter"] = scrape_twitter()
    except Exception as e:
        logger.error(f"Twitter scraper crashed: {e}", exc_info=True)
        results["twitter"] = []

    logger.info("=" * 60)
    logger.info("Starting LinkedIn scrape...")
    try:
        results["linkedin"] = scrape_linkedin()
    except Exception as e:
        logger.error(f"LinkedIn scraper crashed: {e}", exc_info=True)
        results["linkedin"] = []

    logger.info("=" * 60)
    logger.info("Starting Reddit scrape...")
    try:
        results["reddit"] = scrape_reddit()
    except Exception as e:
        logger.error(f"Reddit scraper crashed: {e}", exc_info=True)
        results["reddit"] = []

    return results
