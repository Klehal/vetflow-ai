#!/usr/bin/env python3
"""Offer Strategist Agent — converts clinic data into a specific, believable hook.

Runs after personalizer. For each clinic without an offer_hook, generates:
  - A 1–2 sentence hook based ONLY on verifiable facts (rating, reviews, booking gap)
  - No fake numbers, no exaggeration, no case studies
  - Stored in clinics.offer_hook

The hook is used by caller.py, email templates, and sms_followup.py to make
outreach feel specific rather than mass-blast.
"""

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vetflow.offer_strategist")

DB_PATH = PROJECT_ROOT / "data" / "vetflow_sales.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def clinics_needing_hook(conn) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT id, name, google_rating, review_count, has_online_booking,
                  after_hours_gap, website_quality_score, score, ai_insight, hours_json
           FROM clinics
           WHERE (offer_hook IS NULL OR offer_hook = '')
             AND score >= 40
           ORDER BY score DESC"""
    ).fetchall()]


def _rule_based_hook(clinic: dict) -> str:
    """Generate hook using pure logic — no API call, always works."""
    name     = clinic["name"]
    rating   = clinic.get("google_rating") or 0
    reviews  = clinic.get("review_count") or 0
    no_book  = not clinic.get("has_online_booking")
    aft_hrs  = clinic.get("after_hours_gap", 0)

    parts = []

    if reviews >= 1000:
        parts.append(
            f"With {reviews:,} Google reviews, {name} is one of the highest-volume "
            f"vet clinics in Calgary — a lot of calls coming in every day."
        )
    elif reviews >= 200:
        parts.append(
            f"{name} has {reviews} Google reviews and a {rating}-star rating — "
            f"a busy, established clinic that people actively seek out."
        )
    else:
        parts.append(f"{name} is an active Calgary vet clinic.")

    if no_book and aft_hrs:
        parts.append(
            "Phone is the primary intake channel, and there's no after-hours coverage — "
            "the calls that come in outside business hours currently go unanswered."
        )
    elif no_book:
        parts.append(
            "There's no online booking, so the phone is the main way clients get in touch. "
            "Any call that doesn't get picked up is a booking that doesn't happen."
        )
    elif aft_hrs:
        parts.append(
            "Even with online booking, calls after hours don't have a fallback — "
            "those callers don't get a response until the next business day."
        )
    else:
        parts.append(
            "Even with good systems, calls during busy periods — lunch, evenings, weekends — "
            "often go unanswered without a dedicated follow-up process."
        )

    return " ".join(parts)


def _gpt_hook(client, clinic: dict) -> str:
    """Use GPT to generate a better hook when API is available."""
    name    = clinic["name"]
    rating  = clinic.get("google_rating") or 0
    reviews = clinic.get("review_count") or 0
    no_book = not clinic.get("has_online_booking")
    aft_hrs = clinic.get("after_hours_gap", 0)
    insight = clinic.get("ai_insight") or ""

    prompt = f"""
Write a 1–2 sentence "hook" for a Calgary vet clinic that explains their specific
missed-call problem. Use ONLY the facts provided — no invented numbers, no fake
case studies, no exaggeration.

Clinic: {name}
Google rating: {rating} stars, {reviews} reviews
Has online booking: {"No" if no_book else "Yes"}
After-hours coverage gap: {"Yes" if aft_hrs else "Unknown"}
Additional context: {insight or "None"}

Rules:
- Reference specific, verifiable facts about this clinic
- Sound like an observation, not a sales pitch
- No dollar amounts in first touch
- 1–2 sentences only
- Do NOT start with "I" or "We"

Return ONLY the hook text, nothing else.
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=120,
        )
        return resp.choices[0].message.content.strip().strip('"')
    except Exception as exc:
        logger.warning("GPT hook failed for %s: %s — using rule-based", name, exc)
        return _rule_based_hook(clinic)


def run():
    logger.info("Offer Strategist starting...")
    conn = get_db()
    clinics = clinics_needing_hook(conn)
    logger.info("Clinics needing offer hook: %d", len(clinics))

    if not clinics:
        logger.info("All clinics have hooks. Done.")
        conn.close()
        return

    # Try to use GPT, fall back to rule-based
    client = None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except ImportError:
        logger.warning("openai not installed — using rule-based hooks")

    for clinic in clinics:
        name = clinic["name"]
        if client:
            hook = _gpt_hook(client, clinic)
        else:
            hook = _rule_based_hook(clinic)

        conn.execute(
            "UPDATE clinics SET offer_hook=?, updated_at=? WHERE id=?",
            (hook, datetime.now().isoformat(), clinic["id"]),
        )
        conn.commit()
        logger.info("  [%d] %-40s → hook set", clinic["score"], name)
        logger.info("       %s", hook[:100])

    conn.close()
    logger.info("Offer Strategist done.")


if __name__ == "__main__":
    run()
