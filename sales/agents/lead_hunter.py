"""Lead Hunter Agent — finds Calgary vet clinics with full details."""

import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: load .env from project root and add project root to sys.path
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

import requests  # noqa: E402

from src.leads.google_places import GooglePlacesClient  # noqa: E402
from src.utils.rate_limiter import RateLimiter  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = PROJECT_ROOT / "data" / "vetflow_sales.db"
SCHEMA_PATH = PROJECT_ROOT / "vetflow_sales" / "schema.sql"

# Calgary city centre coordinates
CALGARY_LAT = 51.0447
CALGARY_LNG = -114.0719
CALGARY_LOCATION = (CALGARY_LAT, CALGARY_LNG)
SEARCH_RADIUS_M = 40_000  # 40 km covers greater Calgary

SEARCH_QUERIES = [
    "veterinary clinic Calgary Alberta",
    "animal hospital Calgary",
    "vet clinic Calgary",
    "animal clinic Calgary AB",
]

# Keywords that suggest online booking is available
BOOKING_KEYWORDS = [
    "book online",
    "request appointment",
    "schedule",
    "calendly",
    "vetcove",
    "ezyvet",
    "vetspire",
    "online booking",
    "book an appointment",
    "book appointment",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("vetflow.lead_hunter")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite DB and apply the schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()
    return conn


def place_id_exists(conn: sqlite3.Connection, place_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM clinics WHERE google_place_id = ?", (place_id,)
    ).fetchone()
    return row is not None


def insert_clinic(conn: sqlite3.Connection, data: dict) -> int:
    """Insert a clinic row and return its new id."""
    sql = """
        INSERT INTO clinics (
            name, phone, website, address, city, province,
            google_place_id, google_rating, review_count,
            has_online_booking, has_website, website_quality_score,
            hours_json, after_hours_gap
        ) VALUES (
            :name, :phone, :website, :address, :city, :province,
            :google_place_id, :google_rating, :review_count,
            :has_online_booking, :has_website, :website_quality_score,
            :hours_json, :after_hours_gap
        )
    """
    cur = conn.execute(sql, data)
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Website helpers
# ---------------------------------------------------------------------------

def detect_online_booking(website_url: str) -> bool:
    """Return True if the website appears to offer online booking."""
    if not website_url:
        return False
    try:
        resp = requests.get(
            website_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; VetFlowBot/1.0)"},
            allow_redirects=True,
        )
        text = resp.text.lower()
        return any(kw in text for kw in BOOKING_KEYWORDS)
    except Exception:
        logger.debug("Could not fetch %s for booking detection", website_url)
        return False


def score_website_quality(website_url: str, has_booking: bool) -> int:
    """
    Return a 0-10 website quality score.

    0  = no website
    1-3 = basic/old (no booking, very simple)
    4-6 = decent (professional look but missing features)
    7-10 = modern (online booking, likely responsive)
    """
    if not website_url:
        return 0

    # Start at a mid-range baseline and adjust
    score = 4

    # Online booking is the clearest signal of a modern, maintained site
    if has_booking:
        score += 3

    # Try to probe a few quality signals from the homepage HTML
    try:
        resp = requests.get(
            website_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; VetFlowBot/1.0)"},
            allow_redirects=True,
        )
        html = resp.text.lower()

        # Modern indicators
        if "viewport" in html:
            score += 1  # responsive meta tag
        if any(fw in html for fw in ["bootstrap", "tailwind", "react", "vue", "angular", "next"]):
            score += 1  # modern framework
        if "ssl" in resp.url or resp.url.startswith("https"):
            score += 1  # HTTPS

        # Old/poor indicators
        if "table" in html and html.count("<table") > 5:
            score -= 2  # heavy table layout = old site
        if "marquee" in html or "blink" in html:
            score -= 2  # very old HTML tags

    except Exception:
        # If we can't load it at all, it's pretty bad
        score = max(score - 1, 1)

    return max(0, min(10, score))


# ---------------------------------------------------------------------------
# Hours parsing
# ---------------------------------------------------------------------------

def detect_after_hours_gap(opening_hours: dict) -> int:
    """
    Return 1 if the clinic appears to be closed evenings or weekends.
    Google provides periods as a list of {open: {day, time}, close: {day, time}}.
    day: 0=Sunday … 6=Saturday
    time: "HHMM" 24h string
    """
    if not opening_hours:
        return 0

    periods = opening_hours.get("periods", [])
    if not periods:
        return 0

    open_days = {p["open"]["day"] for p in periods if "open" in p}

    # Check weekends (0=Sunday, 6=Saturday)
    weekend_closed = 0 not in open_days or 6 not in open_days

    # Check evening hours — any day closing before 18:00
    closes_early = False
    for period in periods:
        close = period.get("close", {})
        close_time = close.get("time", "2000")
        try:
            if int(close_time) < 1800:
                closes_early = True
                break
        except ValueError:
            pass

    return 1 if (weekend_closed or closes_early) else 0


# ---------------------------------------------------------------------------
# Main hunt logic
# ---------------------------------------------------------------------------

def run() -> int:
    """Find Calgary vet clinics and store new ones in the DB. Returns new count."""
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not set in environment / .env")

    conn = init_db(DB_PATH)
    rate_limiter = RateLimiter(calls_per_second=2.0)
    client = GooglePlacesClient(api_key=api_key, rate_limiter=rate_limiter)

    seen_place_ids: set[str] = set()
    new_count = 0

    for query in SEARCH_QUERIES:
        logger.info("Searching: %s", query)
        leads = client.search_businesses(
            query=query,
            location=CALGARY_LOCATION,
            radius_m=SEARCH_RADIUS_M,
        )
        logger.info("  → %d results", len(leads))

        for lead in leads:
            place_id = lead.google_place_id
            if not place_id:
                continue
            if place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            if place_id_exists(conn, place_id):
                logger.debug("Already in DB: %s (%s)", lead.business_name, place_id)
                continue

            # Fetch full place details for phone, website, hours
            logger.info("  Fetching details for: %s", lead.business_name)
            details = client.get_place_details(place_id)

            website = details.get("website") or lead.website_url or ""
            phone = details.get("formatted_phone_number") or lead.phone or ""
            address = details.get("formatted_address") or lead.address or ""
            rating = details.get("rating") or lead.rating
            review_count = details.get("user_ratings_total") or lead.review_count or 0
            opening_hours = details.get("opening_hours", {})
            hours_json = json.dumps(opening_hours) if opening_hours else None

            has_website = 1 if website else 0
            after_hours_gap = detect_after_hours_gap(opening_hours)

            # These checks hit the live website — skip if no website
            if website:
                has_booking = detect_online_booking(website)
                quality_score = score_website_quality(website, has_booking)
            else:
                has_booking = False
                quality_score = 0

            row = {
                "name": lead.business_name,
                "phone": phone,
                "website": website,
                "address": address,
                "city": lead.city or "Calgary",
                "province": lead.state or "AB",
                "google_place_id": place_id,
                "google_rating": rating,
                "review_count": review_count,
                "has_online_booking": 1 if has_booking else 0,
                "has_website": has_website,
                "website_quality_score": quality_score,
                "hours_json": hours_json,
                "after_hours_gap": after_hours_gap,
            }

            try:
                insert_clinic(conn, row)
                new_count += 1
                logger.info(
                    "  Saved: %s | website=%s | booking=%s | quality=%d",
                    lead.business_name, bool(website), has_booking, quality_score,
                )
            except sqlite3.IntegrityError:
                logger.debug("Duplicate on insert (race): %s", place_id)

        # Brief pause between query batches to stay within rate limits
        time.sleep(1)

    conn.close()
    logger.info("Lead hunter complete. New clinics added: %d", new_count)
    return new_count


if __name__ == "__main__":
    count = run()
    print(f"\nDone. New Calgary vet clinics added to DB: {count}")
