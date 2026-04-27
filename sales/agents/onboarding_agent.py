#!/usr/bin/env python3
"""Onboarding Agent — prepares a clinic for VetFlow AI deployment.

Triggers when a clinic reaches status='booked' or 'client'.

Generates:
  1. A personalised onboarding checklist (saved to vetflow_sales/onboarding/)
  2. A pre-filled intake form URL (Railway app /intake/{clinic_id})
  3. A setup summary email sent to the clinic contact

Checklist covers:
  - Confirm business hours
  - Confirm after-hours message preference
  - Confirm staff name for SMS replies
  - Connect Twilio number (or port existing)
  - Test missed-call flow
  - Review dashboard
"""

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
logger = logging.getLogger("vetflow.onboarding")

DB_PATH         = PROJECT_ROOT / "data" / "vetflow_sales.db"
OUTPUT_DIR      = PROJECT_ROOT / "vetflow_sales" / "onboarding"
RAILWAY_URL     = "https://vetflow-ai-production.up.railway.app"
FROM_EMAIL      = "vetflow.ai@gmail.com"
FROM_NAME       = "Karan at VetFlow AI"
CALENDLY        = "https://calendly.com/vetflow-ai/15-min-discovery-call"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def clinics_ready_for_onboarding(conn) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT id, name, email, phone, address, city, hours_json,
                  google_rating, review_count, has_online_booking, score
           FROM clinics
           WHERE status IN ('booked', 'client')
             AND onboarding_started = 0"""
    ).fetchall()]


def generate_checklist(clinic: dict) -> str:
    name  = clinic["name"]
    email = clinic.get("email") or "—"
    phone = clinic.get("phone") or "—"

    return f"""
{'='*60}
VETFLOW AI — ONBOARDING CHECKLIST
Clinic: {name}
Contact email: {email}
Phone: {phone}
Date: {datetime.now().strftime('%Y-%m-%d')}
{'='*60}

STEP 1 — CONFIRM CLINIC INFO (Karan collects on onboarding call)
  [ ] Clinic name (as it should appear in texts)
  [ ] Business hours (Mon–Sun, open/close times)
  [ ] After-hours preference (just capture name + number, or full booking?)
  [ ] Staff member name for auto-text sign-off (e.g. "— The {name} team")
  [ ] Owner / manager name for dashboard access
  [ ] Email for dashboard login

STEP 2 — PHONE SETUP
  [ ] Option A: New Twilio number assigned (~$1.15/mo)
  [ ] Option B: Port existing number (1–3 business days)
  [ ] Test inbound call received + SMS fires within 60s

STEP 3 — SYSTEM CONFIGURATION
  [ ] Business hours loaded into VetFlow dashboard
  [ ] After-hours message customised
  [ ] Staff name configured in auto-reply template
  [ ] Emergency keywords set (bleeding, not breathing, poisoning, etc.)

STEP 4 — DASHBOARD ACCESS
  [ ] API key generated for {name}
  [ ] Dashboard login sent to clinic owner
  [ ] Demo walkthrough completed (15 min)
  [ ] Appointment view verified

STEP 5 — GO LIVE
  [ ] Call forwarding / missed-call routing enabled
  [ ] Test: call the clinic number, let it ring → voicemail
  [ ] Verify auto-text fires within 60 seconds
  [ ] Client confirms receipt

STEP 6 — FIRST WEEK CHECK-IN
  [ ] Review first 7 days of captured calls
  [ ] Any custom adjustments to message tone?
  [ ] Confirm billing setup (invoice or card on file)

{'='*60}
INTAKE FORM: {RAILWAY_URL}/intake/[clinic_id_here]
DASHBOARD:   {RAILWAY_URL}/dashboard/?api_key=[api_key_here]
{'='*60}
"""


def send_onboarding_email(to_email: str, clinic_name: str) -> bool:
    subject = f"Welcome to VetFlow AI — next steps for {clinic_name}"
    body = f"""Hi there,

Excited to get you set up!

Here's what happens next:

1. We'll have a quick 15-minute onboarding call to confirm your clinic hours, phone setup, and how you'd like the auto-texts to sound.

2. We'll assign your clinic a dedicated phone number (or port your existing one if you prefer).

3. We'll go live — from that point, every missed call gets an automatic follow-up text within 60 seconds.

The whole setup typically takes less than a day once we have the details from you.

You can book the onboarding call here: {CALENDLY}

If you have any questions before then, just reply to this email.

— Karan
VetFlow AI, Calgary
vetflow.ai@gmail.com
"""
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content
        sg  = SendGridAPIClient(os.getenv("SENDGRID_API_KEY", ""))
        msg = Mail()
        msg.from_email = Email(FROM_EMAIL, FROM_NAME)
        msg.to         = To(to_email)
        msg.subject    = subject
        msg.content    = [Content("text/plain", body)]
        resp = sg.send(msg)
        return resp.status_code in (200, 201, 202)
    except Exception as exc:
        logger.error("SendGrid error: %s", exc)
        return False


def run():
    logger.info("Onboarding Agent starting...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    clinics = clinics_ready_for_onboarding(conn)
    logger.info("Clinics ready for onboarding: %d", len(clinics))

    for clinic in clinics:
        name  = clinic["name"]
        email = clinic.get("email")
        logger.info("  Processing: %s", name)

        # Generate and save checklist
        checklist = generate_checklist(clinic)
        safe_name = name.replace("/", "-").replace(" ", "_")[:40]
        path = OUTPUT_DIR / f"{safe_name}_onboarding.txt"
        path.write_text(checklist, encoding="utf-8")
        logger.info("    Checklist saved → %s", path)

        # Send welcome email if we have an address
        if email:
            ok = send_onboarding_email(email, name)
            logger.info("    Welcome email %s → %s", "sent" if ok else "FAILED", email)

        # Mark started
        conn.execute(
            "UPDATE clinics SET onboarding_started=1, updated_at=? WHERE id=?",
            (datetime.now().isoformat(), clinic["id"]),
        )
        conn.commit()

        print(f"\n{'='*50}")
        print(f"  ONBOARDING STARTED: {name}")
        print(f"  Checklist: {path}")
        print(f"{'='*50}")

    conn.close()
    logger.info("Onboarding Agent done.")


if __name__ == "__main__":
    run()
