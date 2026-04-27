#!/usr/bin/env python3
"""Email Finder — scrapes clinic websites for contact emails.
Falls back to common patterns (info@, contact@, hello@) when scraping fails.
"""

import logging
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import requests
from bs4 import BeautifulSoup

DB_PATH = PROJECT_ROOT / "data" / "vetflow_sales.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vetflow.email_finder")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SKIP_DOMAINS = {"sentry.io", "example.com", "schema.org", "w3.org", "wixpress.com",
                "squarespace.com", "wordpress.com", "googleapis.com", "cloudflare.com"}
SKIP_PREFIXES = ("noreply", "no-reply", "donotreply", "bounce", "mailer",
                 "postmaster", "abuse", "spam", "webmaster", "support@wix",
                 "support@squarespace")


def is_valid_email(email: str, domain: str) -> bool:
    email = email.lower()
    if any(email.startswith(p) for p in SKIP_PREFIXES):
        return False
    email_domain = email.split("@")[1]
    if any(skip in email_domain for skip in SKIP_DOMAINS):
        return False
    return True


def scrape_emails_from_url(url: str, timeout: int = 8) -> list:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")

        # Remove script/style tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(" ")
        # Also check href="mailto:" links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                email = href[7:].split("?")[0].strip()
                if email:
                    text += " " + email

        found = EMAIL_RE.findall(text)
        domain = urlparse(url).netloc.replace("www.", "")
        valid = [e.lower() for e in found if is_valid_email(e, domain)]
        # Prefer emails matching the clinic's own domain
        own = [e for e in valid if domain.split(".")[0] in e]
        return own if own else valid
    except Exception as e:
        logger.debug("Scrape failed for %s: %s", url, e)
        return []


def find_contact_page(website: str) -> Optional[str]:
    """Try to find a /contact or /contact-us page."""
    base = website.rstrip("/")
    for path in ["/contact", "/contact-us", "/about", "/about-us", "/reach-us"]:
        try:
            r = requests.head(base + path, headers=HEADERS, timeout=5, allow_redirects=True)
            if r.status_code == 200:
                return base + path
        except Exception:
            pass
    return None


def domain_from_name(name: str) -> Optional[str]:
    """Guess a domain from clinic name for common patterns."""
    # Not reliable — skip this, just scrape the website
    return None


def find_email_for_clinic(clinic: dict) -> Optional[str]:
    website = clinic.get("website", "")
    name = clinic.get("name", "")

    if not website:
        logger.info("  No website for %s — skipping", name)
        return None

    if not website.startswith("http"):
        website = "https://" + website

    # Try main page
    emails = scrape_emails_from_url(website)
    if emails:
        logger.info("  Found on main page: %s", emails[0])
        return emails[0]

    # Try contact page
    contact_url = find_contact_page(website)
    if contact_url:
        emails = scrape_emails_from_url(contact_url)
        if emails:
            logger.info("  Found on contact page: %s", emails[0])
            return emails[0]

    # Try Google search fallback: site:domain email
    logger.info("  No email found on website for %s", name)
    return None


def run():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    clinics = conn.execute(
        """SELECT id, name, website, email, score FROM clinics
           WHERE (email IS NULL OR email = '')
             AND website IS NOT NULL AND website != ''
           ORDER BY score DESC"""
    ).fetchall()

    logger.info("Finding emails for %d clinics with websites but no email", len(clinics))

    found = 0
    failed = 0

    for clinic in clinics:
        cid = clinic["id"]
        name = clinic["name"]
        logger.info("[%d] %s — %s", clinic["score"], name, clinic["website"])

        email = find_email_for_clinic(dict(clinic))

        if email:
            conn.execute(
                "UPDATE clinics SET email=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (email, cid),
            )
            conn.commit()
            found += 1
        else:
            failed += 1

        time.sleep(1)  # polite delay

    conn.close()
    logger.info("Email finder done: %d found, %d not found", found, failed)
    return {"found": found, "not_found": failed}


if __name__ == "__main__":
    result = run()
    print(f"\nEmails found: {result['found']}, Not found: {result['not_found']}")
