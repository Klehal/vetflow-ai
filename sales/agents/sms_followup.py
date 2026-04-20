#!/usr/bin/env python3
"""SMS Follow-up Agent — sends texts to clinics that were called but didn't pick up.

Runs ~30 minutes after caller.py. Looks for clinics with a 'queued' SMS touchpoint
(set by caller.py) and sends the follow-up message via Twilio.

Also handles Day-3 SMS follow-ups for clinics that received Day-1 email but no reply.
"""

import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vetflow.sms_followup")

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH          = PROJECT_ROOT / "data" / "vetflow_sales.db"
TWILIO_SID       = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN     = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_PHONE       = os.getenv("TWILIO_PHONE_NUMBER", "")
MAX_SMS_PER_RUN  = 15
DELAY_BETWEEN    = 2   # seconds
CALENDLY_LINK    = "https://calendly.com/vetflow-ai/15-min-discovery-call"

# Minimum minutes after call before sending SMS (avoid texting mid-conversation)
SMS_DELAY_MINUTES = 30


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_queued_sms(conn: sqlite3.Connection, limit: int) -> list:
    """Get clinics where caller.py queued an SMS and delay has passed."""
    cutoff = (datetime.now() - timedelta(minutes=SMS_DELAY_MINUTES)).isoformat()
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.phone, c.score, t.id as tp_id
        FROM clinics c
        JOIN touchpoints t ON t.clinic_id = c.id
        WHERE t.channel = 'sms'
          AND t.direction = 'outbound'
          AND t.status = 'queued'
          AND t.created_at <= ?
          AND c.status NOT IN ('dead', 'unsubscribed', 'client')
        ORDER BY c.score DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_sms_sent(conn: sqlite3.Connection, tp_id: int, msg_sid: str, body: str):
    conn.execute(
        "UPDATE touchpoints SET status='sent', body=?, twilio_sid=?, sent_at=? WHERE id=?",
        (body, msg_sid, datetime.now().isoformat(), tp_id),
    )
    conn.commit()


def mark_sms_failed(conn: sqlite3.Connection, tp_id: int):
    conn.execute(
        "UPDATE touchpoints SET status='failed', sent_at=? WHERE id=?",
        (datetime.now().isoformat(), tp_id),
    )
    conn.commit()


# ── Twilio ────────────────────────────────────────────────────────────────────

def normalize_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    if not digits.startswith("1"):
        digits = "1" + digits
    return f"+{digits}"


def send_twilio_sms(to: str, body: str) -> str:
    """Send SMS via Twilio REST API using curl. Returns message SID."""
    import subprocess, json, urllib.parse
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    data = urllib.parse.urlencode({
        "From": FROM_PHONE,
        "To":   to,
        "Body": body,
    })
    cmd = [
        "curl", "-s", "-X", "POST", url,
        "-u", f"{TWILIO_SID}:{TWILIO_TOKEN}",
        "--data", data,
        "--max-time", "20",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    resp = json.loads(proc.stdout)
    if resp.get("status") in ("queued", "sent") or resp.get("sid"):
        return resp.get("sid", "")
    raise RuntimeError(f"Twilio error: {resp.get('message', proc.stdout)}")


# ── Message builders ──────────────────────────────────────────────────────────

def post_call_sms(clinic_name: str) -> str:
    """Instant follow-up after a missed call — curiosity hook, no pitch."""
    return (
        f"Hey, just tried calling {clinic_name}. Quick question — when you miss a call, "
        f"do you guys currently text them back or does it go to voicemail? — Karan, VetFlow AI"
    )


def followup_24h_sms(clinic_name: str) -> str:
    """24-hour follow-up if no reply to the first SMS."""
    return (
        f"Built a simple system for vet clinics in Calgary that captures missed calls "
        f"and turns them into booked appointments automatically. "
        f"Happy to show you how it'd work for {clinic_name}: {CALENDLY_LINK}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    if not TWILIO_SID or not TWILIO_TOKEN or not FROM_PHONE:
        logger.error("Twilio credentials missing — set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER")
        return

    logger.info("=" * 60)
    logger.info("VETFLOW SMS FOLLOW-UP — %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 60)

    conn = get_db()
    queued = get_queued_sms(conn, limit=MAX_SMS_PER_RUN)
    logger.info("Queued SMS to send: %d (min %d min delay after call)", len(queued), SMS_DELAY_MINUTES)

    sent = 0
    failed = 0

    for clinic in queued:
        name  = clinic["name"]
        phone = normalize_phone(clinic["phone"])
        tp_id = clinic["tp_id"]
        body  = post_call_sms(name)

        logger.info("  SMS → %-42s  %s", name, phone)
        try:
            sid = send_twilio_sms(phone, body)
            mark_sms_sent(conn, tp_id, sid, body)
            logger.info("       → sent  sid=%s", sid)
            sent += 1
        except Exception as exc:
            logger.error("       → FAILED: %s", exc)
            mark_sms_failed(conn, tp_id)
            failed += 1

        if len(queued) > 1:
            time.sleep(DELAY_BETWEEN)

    conn.close()
    logger.info("SMS follow-up done: %d sent, %d failed", sent, failed)


if __name__ == "__main__":
    run()
