#!/usr/bin/env python3
"""First Client Mode — Tier A only (score 75+).

Generates a fully custom call script, SMS, and email for each of the top
4 Calgary vet clinics. Outputs them to vetflow_sales/tier_a/ for review,
then optionally places the calls and sends emails.

Run manually when you want to go deep on the top targets.

Usage:
    python vetflow_sales/agents/first_client_mode.py
    python vetflow_sales/agents/first_client_mode.py --call    # place calls now
    python vetflow_sales/agents/first_client_mode.py --email   # send emails now
"""

import argparse
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vetflow.first_client_mode")

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH        = PROJECT_ROOT / "data" / "vetflow_sales.db"
OUTPUT_DIR     = PROJECT_ROOT / "vetflow_sales" / "tier_a"
BLAND_API_URL  = "https://api.bland.ai/v1/calls"
BLAND_API_KEY  = os.getenv(
    "BLAND_API_KEY",
    "org_d6bccd2c594e03fd9fe851eb6dafaf6e9e442d92f2626c42a979ed7eb3253da0ebfb165704cbe107b49469",
)
CALENDLY_LINK  = "https://calendly.com/vetflow-ai/15-min-discovery-call"
FROM_EMAIL     = "vetflow.ai@gmail.com"
FROM_NAME      = "Karan at VetFlow AI"
TIER_A_SCORE   = 75


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_tier_a_clinics(conn):
    return [dict(r) for r in conn.execute(
        """SELECT * FROM clinics WHERE score >= ? ORDER BY score DESC, review_count DESC""",
        (TIER_A_SCORE,),
    ).fetchall()]


def already_called(conn, clinic_id) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM touchpoints WHERE clinic_id=? AND channel='call'",
        (clinic_id,),
    ).fetchone())


# ── GPT personalisation ───────────────────────────────────────────────────────

def generate_custom_scripts(clinic: dict) -> dict:
    """Use GPT-4o-mini to generate fully custom call, SMS, and email for one clinic."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except ImportError:
        logger.error("openai package not installed")
        return {}

    name      = clinic["name"]
    rating    = clinic.get("google_rating") or 0
    reviews   = clinic.get("review_count") or 0
    no_book   = not clinic.get("has_online_booking")
    after_hrs = clinic.get("after_hours_gap", 0)
    insight   = clinic.get("ai_insight") or ""

    context = (
        f"Clinic: {name}\n"
        f"Google rating: {rating} stars, {reviews} reviews\n"
        f"Online booking available: {'No' if no_book else 'Yes'}\n"
        f"After-hours coverage gap: {'Yes' if after_hrs else 'Unknown'}\n"
        f"Additional insight: {insight or 'None'}\n"
    )

    prompt = f"""
You are a world-class B2B sales copywriter specialising in veterinary clinic outreach.

Given this Calgary vet clinic profile, write THREE personalised assets:
{context}

RULES:
- Sound like a real local person named Karan, NOT a vendor
- NO dollar amounts or revenue claims in first touch
- NO "AI receptionist" language — say "missed call recovery system" if needed
- NO fake case studies or unverifiable claims
- Every asset must reference something SPECIFIC about this clinic
- Call script must be deliverable in under 25 seconds of speech
- Calendly link: {CALENDLY_LINK}

Return ONLY valid JSON with these keys:
{{
  "call_task": "full instruction for Bland.ai voice agent",
  "call_first_sentence": "opening line only",
  "sms": "single SMS message under 160 chars — no pitch, just curiosity question referencing the clinic",
  "email_subject": "subject line",
  "email_body": "plain text email body, 5-7 sentences max, observational not accusatory"
}}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return json.loads(resp.choices[0].message.content)


# ── Save output ───────────────────────────────────────────────────────────────

def save_clinic_brief(clinic: dict, scripts: dict):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = clinic["name"].replace("/", "-").replace(" ", "_")[:40]
    path = OUTPUT_DIR / f"{safe_name}.txt"

    content = f"""
{'='*60}
TIER A — FIRST CLIENT MODE
Clinic: {clinic['name']}
Score:  {clinic['score']}  |  Rating: {clinic.get('google_rating')} ★  |  Reviews: {clinic.get('review_count')}
Phone:  {clinic.get('phone')}
Email:  {clinic.get('email') or 'NOT FOUND'}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{'='*60}

── CALL SCRIPT ──────────────────────────────────────────
First sentence: {scripts.get('call_first_sentence', '')}

Full task:
{scripts.get('call_task', '')}

── SMS ──────────────────────────────────────────────────
{scripts.get('sms', '')}

── EMAIL ────────────────────────────────────────────────
Subject: {scripts.get('email_subject', '')}

{scripts.get('email_body', '')}
{'='*60}
"""
    path.write_text(content.strip(), encoding="utf-8")
    return path


# ── Place call ────────────────────────────────────────────────────────────────

def normalize_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    if not digits.startswith("1"):
        digits = "1" + digits
    return f"+{digits}"


def place_bland_call(clinic: dict, scripts: dict) -> tuple:
    payload = {
        "phone_number":      normalize_phone(clinic["phone"]),
        "task":              scripts["call_task"],
        "voice":             "mason",
        "first_sentence":    scripts["call_first_sentence"],
        "wait_for_greeting": True,
        "max_duration":      180,
        "record":            True,
        "webhook":           None,
    }
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST", BLAND_API_URL,
        "-H", f"Authorization: {BLAND_API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        "--max-time", "30",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    *body_lines, code = proc.stdout.strip().split("\n")
    body = "\n".join(body_lines)
    if int(code) >= 400:
        raise RuntimeError(f"Bland.ai HTTP {code}: {body}")
    data = json.loads(body)
    return data.get("call_id", ""), data.get("status", "initiated")


def record_call(conn, clinic_id: int, phone: str, call_id: str, status: str):
    conn.execute(
        """INSERT INTO touchpoints
               (clinic_id, channel, direction, sequence_day, subject, body,
                sent_at, status, bland_call_id, created_at)
           VALUES (?, 'call', 'outbound', 1,
                   'Tier A custom call', 'First client mode — personalised script',
                   ?, ?, ?, ?)""",
        (clinic_id, datetime.now().isoformat(), status, call_id,
         datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE clinics SET status='contacted', updated_at=? WHERE id=? AND status='new'",
        (datetime.now().isoformat(), clinic_id),
    )
    conn.commit()


# ── Send email ────────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY", ""))
        msg = Mail()
        msg.from_email = Email(FROM_EMAIL, FROM_NAME)
        msg.to = To(to_email)
        msg.subject = subject
        msg.content = [Content("text/plain", body)]
        resp = sg.send(msg)
        return resp.status_code in (200, 201, 202)
    except Exception as exc:
        logger.error("SendGrid error: %s", exc)
        return False


def record_email(conn, clinic_id: int, subject: str, body: str, ok: bool):
    conn.execute(
        """INSERT INTO touchpoints
               (clinic_id, channel, direction, sequence_day, subject, body,
                sent_at, status, created_at)
           VALUES (?, 'email', 'outbound', 1, ?, ?, ?, ?, ?)""",
        (clinic_id, subject, body, datetime.now().isoformat(),
         "sent" if ok else "failed", datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE clinics SET status='contacted', updated_at=? WHERE id=? AND status='new'",
        (datetime.now().isoformat(), clinic_id),
    )
    conn.commit()


# ── Main ──────────────────────────────────────────────────────────────────────

def run(do_call: bool = False, do_email: bool = False):
    logger.info("=" * 60)
    logger.info("FIRST CLIENT MODE — Tier A Only")
    logger.info("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    clinics = get_tier_a_clinics(conn)

    logger.info("Tier A clinics found: %d", len(clinics))
    if not clinics:
        logger.info("No Tier A clinics. Exiting.")
        conn.close()
        return

    for clinic in clinics:
        name = clinic["name"]
        logger.info("\nProcessing: %s (score=%d)", name, clinic["score"])

        # Generate custom scripts
        logger.info("  Generating custom scripts via GPT-4o-mini...")
        scripts = generate_custom_scripts(clinic)
        if not scripts:
            logger.warning("  GPT failed for %s — skipping", name)
            continue

        # Save brief
        path = save_clinic_brief(clinic, scripts)
        logger.info("  Brief saved → %s", path)

        # Place call if requested and not already called
        if do_call:
            if not clinic.get("phone"):
                logger.warning("  No phone for %s — skipping call", name)
            elif already_called(conn, clinic["id"]):
                logger.info("  Already called %s — skipping", name)
            else:
                try:
                    call_id, status = place_bland_call(clinic, scripts)
                    record_call(conn, clinic["id"], clinic["phone"], call_id, status)
                    logger.info("  Call placed → call_id=%s", call_id)
                    time.sleep(8)
                except Exception as exc:
                    logger.error("  Call failed: %s", exc)

        # Send email if requested and clinic has one
        if do_email:
            email = clinic.get("email")
            if not email:
                logger.info("  No email for %s — skipping email", name)
            else:
                subject = scripts.get("email_subject", f"Quick question — {name}")
                body    = scripts.get("email_body", "")
                ok      = send_email(email, subject, body)
                record_email(conn, clinic["id"], subject, body, ok)
                logger.info("  Email %s → %s", "sent" if ok else "FAILED", email)

        print(f"\n{'─'*60}")
        print(f"TIER A BRIEF: {name}")
        print(f"{'─'*60}")
        print(f"CALL: {scripts.get('call_first_sentence', '')}")
        print(f"SMS:  {scripts.get('sms', '')}")
        print(f"SUBJ: {scripts.get('email_subject', '')}")
        print(f"{'─'*60}\n")

    conn.close()
    logger.info("First client mode complete. Briefs in: %s", OUTPUT_DIR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--call",  action="store_true", help="Place Bland.ai calls")
    parser.add_argument("--email", action="store_true", help="Send emails")
    args = parser.parse_args()
    run(do_call=args.call, do_email=args.email)
