#!/usr/bin/env python3
"""Caller Agent — call-first engine for Calgary vet clinics.

Priority order:
  Tier A (score 75+) → called with fully personalised script
  Tier B (40–74)     → called with standard curiosity script
  Tier C (<40)       → skipped

After each call a follow-up SMS is queued in the DB for sms_followup.py
to send 30 minutes later (avoids texting someone mid-conversation).
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from vetflow_sales.agents.coordinator import Coordinator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vetflow.caller")

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH       = PROJECT_ROOT / "data" / "vetflow_sales.db"
BLAND_API_URL = "https://api.bland.ai/v1/calls"
BLAND_API_KEY = os.getenv(
    "BLAND_API_KEY",
    "org_d6bccd2c594e03fd9fe851eb6dafaf6e9e442d92f2626c42a979ed7eb3253da0ebfb165704cbe107b49469",
)
CALENDLY_LINK     = "https://calendly.com/vetflow-ai/15-min-discovery-call"
MAX_CALLS_PER_RUN = 10
DELAY_BETWEEN_CALLS = 6   # seconds
TIER_A_SCORE      = 75
TIER_B_SCORE      = 40    # minimum


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_callable_clinics(conn: sqlite3.Connection, limit: int) -> list:
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.phone, c.city, c.score,
               c.ai_insight, c.missed_revenue_estimate,
               c.google_rating, c.review_count, c.has_online_booking,
               c.after_hours_gap, c.status
        FROM clinics c
        WHERE c.phone IS NOT NULL AND c.phone != ''
          AND c.score >= ?
          AND c.status NOT IN ('lost', 'unsubscribed', 'client', 'dead')
          AND NOT EXISTS (
              SELECT 1 FROM touchpoints t
              WHERE t.clinic_id = c.id AND t.channel = 'call'
          )
        ORDER BY c.score DESC, c.created_at ASC
        LIMIT ?
        """,
        (TIER_B_SCORE, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def record_touchpoint(conn: sqlite3.Connection, clinic_id: int, phone: str,
                      call_id: str, status: str):
    conn.execute(
        """INSERT INTO touchpoints
               (clinic_id, channel, direction, sequence_day, subject, body,
                sent_at, status, bland_call_id, created_at)
           VALUES (?, 'call', 'outbound', 1,
                   'Cold call', 'AI cold call — VetFlow missed-call pitch',
                   ?, ?, ?, ?)""",
        (clinic_id, datetime.now().isoformat(), status, call_id,
         datetime.now().isoformat()),
    )
    conn.commit()


def queue_sms_followup(conn: sqlite3.Connection, clinic_id: int):
    """Mark this clinic for SMS follow-up (sms_followup.py will send it ~30 min later)."""
    conn.execute(
        """INSERT OR IGNORE INTO touchpoints
               (clinic_id, channel, direction, sequence_day, subject, body,
                sent_at, status, created_at)
           VALUES (?, 'sms', 'outbound', 1,
                   'SMS follow-up queued', '',
                   NULL, 'queued', ?)""",
        (clinic_id, datetime.now().isoformat()),
    )
    conn.commit()


def mark_contacted(conn: sqlite3.Connection, clinic_id: int):
    conn.execute(
        "UPDATE clinics SET status='contacted', updated_at=? WHERE id=? AND status='new'",
        (datetime.now().isoformat(), clinic_id),
    )
    conn.commit()


# ── Phone ─────────────────────────────────────────────────────────────────────

def normalize_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    if not digits.startswith("1"):
        digits = "1" + digits
    return f"+{digits}"


# ── Call scripts ──────────────────────────────────────────────────────────────

def _tier_a_script(clinic: dict) -> tuple:
    """Fully personalised script for Tier A (score 75+) clinics."""
    name    = clinic["name"]
    rating  = clinic.get("google_rating") or 4.5
    reviews = clinic.get("review_count") or 0
    no_booking = not clinic.get("has_online_booking")

    # Build a specific hook based on what we know
    if reviews >= 500:
        context_hook = (
            f"I was looking at your Google reviews — {reviews} reviews and a {rating}-star rating. "
            f"That kind of volume means you're handling a lot of calls every day."
        )
    else:
        context_hook = (
            f"I noticed {name} has {reviews} reviews on Google — clearly a busy clinic."
        )

    booking_hook = (
        " And I couldn't find an online booking option on your site, "
        "so I imagine the phone is your main intake channel."
        if no_booking else
        " Even with online booking, a lot of calls still come in that don't get captured."
    )

    task = (
        f"You are making a short, friendly, LOCAL sales call on behalf of VetFlow AI in Calgary. "
        f"You are calling {name}. Sound like a real person — warm, unhurried, curious. "
        f"Do NOT sound like a robot or a sales script. Keep the call under 2 minutes unless "
        f"they want to talk longer.\n\n"
        f"CONTEXT YOU KNOW about this clinic:\n"
        f"- {context_hook}\n"
        f"- {booking_hook}\n\n"
        f"YOUR ONLY GOAL: create genuine curiosity about one thing — what happens to missed calls.\n\n"
        f"STRUCTURE:\n"
        f"1. Quick intro: 'Hey, my name's Karan — I'm local, calling from Calgary.'\n"
        f"2. Curiosity question: 'Quick question — when your clinic gets busy or it's after hours "
        f"and a call comes in, what happens to that caller? Do they get a text back or does it "
        f"just go to voicemail?'\n"
        f"3. Pause and listen. Respond naturally to what they say.\n"
        f"4. If they engage: 'I built a simple system that automatically texts those missed callers "
        f"back within 60 seconds and helps capture the booking — works 24/7. No extra staff.'\n"
        f"5. Close softly: 'I actually put together a quick example showing exactly how it would "
        f"work for your clinic — takes about 60 seconds to look at. Want me to send it over?'\n"
        f"6. If yes: 'Great — what's the best email to send it to?' (if unknown) OR "
        f"'Perfect, I'll send it right now.' Then end the call warmly.\n"
        f"7. If they want to book directly: 'Absolutely — I'll send you a booking link too: {CALENDLY_LINK}'\n"
        f"8. If gatekeeper: 'Totally — who's the best person to talk to about missed calls "
        f"and front-desk coverage? The owner or clinic manager?'\n"
        f"9. If not interested: Thank them warmly, wish them a great day, end the call.\n\n"
        f"NEVER mention price. NEVER give a formal pitch. NEVER use the phrase 'AI receptionist'. "
        f"The goal is to get them to say YES to seeing the example — NOT to book a call immediately. "
        f"Sound like a helpful local person, not a vendor."
    )

    first_sentence = (
        f"Hey, quick question — is this the team at {name}?"
    )
    return task, first_sentence


def _tier_b_script(clinic: dict) -> tuple:
    """Standard curiosity script for Tier B (40–74) clinics — under 25 seconds."""
    name = clinic["name"]

    task = (
        f"You are making a short, friendly call on behalf of VetFlow AI in Calgary. "
        f"You are calling {name}. Sound like a real local person — not a sales robot.\n\n"
        f"Keep the ENTIRE call under 2 minutes. Your goal is ONE thing: create curiosity "
        f"about what happens to missed calls.\n\n"
        f"STRUCTURE:\n"
        f"1. After they answer: 'Hi — my name's Karan, I'm local, calling from Calgary. "
        f"Super quick question.'\n"
        f"2. Hook: 'When things get busy or it's after hours and a call comes in that no one "
        f"can get to — what happens? Does that caller get a text back, or does it usually "
        f"just go to voicemail?'\n"
        f"3. Listen. Respond naturally.\n"
        f"4. If they engage: 'Yeah — I built a simple system that texts back missed callers "
        f"within 60 seconds and captures the booking. Works 24/7, no extra staff.'\n"
        f"5. Close softly: 'I can put together a quick example showing exactly how it would "
        f"work for your clinic — takes 60 seconds to look at. Want me to send it over?'\n"
        f"6. If yes: 'Great — what's the best email?' or 'I'll send it right now.' End warmly.\n"
        f"7. If they want a call directly: '{CALENDLY_LINK}'\n"
        f"8. If gatekeeper: 'No worries — who's the best person for that? Owner or manager?'\n"
        f"9. If no: Thank them, end warmly.\n\n"
        f"NEVER mention price, AI, or 'receptionist'. "
        f"Goal is YES to seeing the example — NOT booking a call right away. Sound human and local."
    )

    first_sentence = (
        f"Hey, quick question — is this {name}?"
    )
    return task, first_sentence


def build_call_payload(clinic: dict) -> dict:
    score = clinic.get("score", 0)
    if score >= TIER_A_SCORE:
        task, first_sentence = _tier_a_script(clinic)
    else:
        task, first_sentence = _tier_b_script(clinic)

    return {
        "phone_number":     normalize_phone(clinic["phone"]),
        "task":             task,
        "voice":            "mason",
        "first_sentence":   first_sentence,
        "wait_for_greeting": True,
        "max_duration":     180,
        "record":           True,
        "webhook":          None,
    }


def place_call(clinic: dict) -> tuple:
    payload = build_call_payload(clinic)
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST", BLAND_API_URL,
        "-H", f"Authorization: {BLAND_API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        "--max-time", "30",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    *body_lines, http_code = proc.stdout.strip().split("\n")
    body = "\n".join(body_lines)
    http_code = int(http_code)
    if http_code >= 400:
        raise RuntimeError(f"Bland.ai HTTP {http_code}: {body}")
    data = json.loads(body)
    return data.get("call_id", ""), data.get("status", "initiated")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("VETFLOW CALLER — %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 60)

    conn = get_db()
    clinics = get_callable_clinics(conn, limit=MAX_CALLS_PER_RUN)

    tier_a = [c for c in clinics if c["score"] >= TIER_A_SCORE]
    tier_b = [c for c in clinics if c["score"] < TIER_A_SCORE]
    logger.info(
        "Callable: %d total  |  Tier A: %d  |  Tier B: %d",
        len(clinics), len(tier_a), len(tier_b),
    )

    if not clinics:
        logger.info("All Calgary clinics have been called. Nothing to do.")
        conn.close()
        return

    coordinator = Coordinator(conn)
    successes = 0
    failures  = 0
    skipped   = 0

    for i, clinic in enumerate(clinics, start=1):
        name  = clinic["name"]
        phone = normalize_phone(clinic["phone"])
        tier  = "A" if clinic["score"] >= TIER_A_SCORE else "B"

        # ── Coordinator safety gate ───────────────────────────────────────
        ok, reason = coordinator.safe_to_call(clinic)
        if not ok:
            logger.info(
                "[%d/%d] SKIP | %-42s reason: %s",
                i, len(clinics), name, reason,
            )
            skipped += 1
            continue

        logger.info(
            "[%d/%d] Tier %s | %-42s score=%d  %s",
            i, len(clinics), tier, name, clinic["score"], phone,
        )

        try:
            call_id, status = place_call(clinic)
            record_touchpoint(conn, clinic["id"], phone, call_id, status)
            queue_sms_followup(conn, clinic["id"])
            mark_contacted(conn, clinic["id"])
            logger.info("     → OK  call_id=%s", call_id)
            successes += 1
        except Exception as exc:
            logger.error("     → FAILED: %s", exc)
            record_touchpoint(conn, clinic["id"], phone, "", "error")
            failures += 1

        if i < len(clinics):
            time.sleep(DELAY_BETWEEN_CALLS)

    conn.close()
    logger.info("=" * 60)
    logger.info("DONE: %d placed, %d failed, %d skipped by coordinator", successes, failures, skipped)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
