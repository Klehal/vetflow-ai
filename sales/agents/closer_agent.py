#!/usr/bin/env python3
"""Closer Agent — moves warm leads from 'interested' or 'curious' to a booked demo.

Two-step CTA strategy:
  Step 1 — Send proof page: "I put together a quick example for your clinic"
  Step 2 — After proof page sent: push to Calendly booking

This agent checks replies classified as 'interested' or 'curious' that haven't
been followed up yet (handled=0), sends the proof page, and logs the action.

For 'objection' replies it generates a short, empathetic reframe.
For 'wrong_person' it asks who the right person is.
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
logger = logging.getLogger("vetflow.closer")

DB_PATH       = PROJECT_ROOT / "data" / "vetflow_sales.db"
CALENDLY      = "https://calendly.com/vetflow-ai/15-min-discovery-call"
FROM_EMAIL    = "vetflow.ai@gmail.com"
FROM_NAME     = "Karan at VetFlow AI"
HOT_LEADS_FILE = PROJECT_ROOT / "vetflow_sales" / "hot_leads.txt"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def unhandled_warm_leads(conn) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT r.id as reply_id, r.clinic_id, r.body, r.classification,
                  c.name, c.email, c.proof_page_url, c.offer_hook
           FROM replies r
           JOIN clinics c ON c.id = r.clinic_id
           WHERE r.handled = 0
             AND r.classification IN ('interested', 'curious', 'objection', 'wrong_person')
           ORDER BY r.received_at ASC"""
    ).fetchall()]


def mark_handled(conn, reply_id: int, note: str):
    conn.execute(
        "UPDATE replies SET handled=1 WHERE id=?", (reply_id,)
    )
    conn.execute(
        "UPDATE clinics SET closer_note=?, updated_at=? WHERE id=(SELECT clinic_id FROM replies WHERE id=?)",
        (note, datetime.now().isoformat(), reply_id),
    )
    conn.commit()


def update_clinic_status(conn, clinic_id: int, status: str):
    conn.execute(
        "UPDATE clinics SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(), clinic_id),
    )
    conn.commit()


def send_email(to_email: str, subject: str, body: str) -> bool:
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


def compose_reply(lead: dict) -> tuple:
    """Return (subject, body) based on classification. Two-step CTA."""
    name            = lead["name"]
    classification  = lead["classification"]
    proof_url       = lead.get("proof_page_url") or ""
    original_reply  = lead.get("body", "")[:200]

    if classification == "interested":
        subject = f"Re: {name}"
        if proof_url and proof_url.startswith("http"):
            body = (
                f"Great to hear from you!\n\n"
                f"I actually put together a quick example showing exactly how it would "
                f"work for {name} — takes about 60 seconds to look at:\n\n"
                f"{proof_url}\n\n"
                f"If it makes sense, here's a link to grab a quick call: {CALENDLY}\n\n"
                f"— Karan"
            )
        else:
            # No proof page yet — go straight to Calendly
            body = (
                f"Great to hear from you!\n\n"
                f"Happy to show you how it would work for {name} specifically. "
                f"Here's a link to grab a 15-minute slot:\n\n"
                f"{CALENDLY}\n\n"
                f"— Karan"
            )

    elif classification == "curious":
        subject = f"Re: {name}"
        if proof_url and proof_url.startswith("http"):
            body = (
                f"Good question — I put together a quick example that shows the exact "
                f"flow for {name}. Worth a look:\n\n"
                f"{proof_url}\n\n"
                f"Happy to answer any questions. If it looks interesting, "
                f"you can grab a time here: {CALENDLY}\n\n"
                f"— Karan"
            )
        else:
            body = (
                f"Happy to explain more.\n\n"
                f"The short version: when a call comes in and no one picks up, "
                f"the system automatically texts the caller within 60 seconds and "
                f"helps capture the booking. Works 24/7, no extra staff.\n\n"
                f"Would it be worth 15 minutes to see how it fits {name}? {CALENDLY}\n\n"
                f"— Karan"
            )

    elif classification == "objection":
        subject = f"Re: {name}"
        body = (
            f"Totally understand — and I appreciate you taking the time to reply.\n\n"
            f"Happy to address that directly. Would it be worth 15 minutes "
            f"to see whether it actually applies to your situation? "
            f"No pressure either way.\n\n"
            f"{CALENDLY}\n\n"
            f"— Karan"
        )

    elif classification == "wrong_person":
        subject = f"Re: {name}"
        body = (
            f"Thanks for letting me know — appreciate the heads up.\n\n"
            f"Who would be the best person to reach about front-desk coverage "
            f"and missed calls? Happy to reach out to them directly so I'm not "
            f"taking up your time.\n\n"
            f"— Karan"
        )

    else:
        return None, None

    return subject, body


def log_hot_lead(name: str, email: str, classification: str, reply_sent: str):
    HOT_LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n{'─'*60}\n"
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] CLOSER ACTION\n"
        f"Clinic:     {name}\n"
        f"Email:      {email}\n"
        f"Signal:     {classification.upper()}\n"
        f"Reply sent: {reply_sent[:120]}\n"
    )
    with open(HOT_LEADS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def run():
    logger.info("Closer Agent starting...")
    conn = get_db()
    leads = unhandled_warm_leads(conn)
    logger.info("Unhandled warm leads: %d", len(leads))

    if not leads:
        logger.info("No warm leads to process. Done.")
        conn.close()
        return

    for lead in leads:
        name           = lead["name"]
        email          = lead.get("email")
        classification = lead["classification"]
        reply_id       = lead["reply_id"]
        clinic_id      = lead["clinic_id"]

        logger.info("  %-40s  [%s]", name, classification.upper())

        if not email:
            logger.warning("    No email for %s — logging only", name)
            mark_handled(conn, reply_id, f"No email — {classification} signal logged")
            continue

        subject, body = compose_reply(lead)
        if not body:
            mark_handled(conn, reply_id, "No action — classification not actionable")
            continue

        ok = send_email(email, subject, body)
        if ok:
            logger.info("    → Reply sent to %s", email)
            note = f"Closer reply sent ({classification}) on {datetime.now().strftime('%Y-%m-%d')}"
            mark_handled(conn, reply_id, note)

            if classification in ("interested", "curious"):
                update_clinic_status(conn, clinic_id, "interested")
                log_hot_lead(name, email, classification, body)

            print(f"\n{'='*50}")
            print(f"  CLOSER: {name} [{classification.upper()}]")
            print(f"  Email:  {email}")
            print(f"  Sent:   {subject}")
            print(f"{'='*50}")
        else:
            logger.error("    → Email send FAILED for %s", name)

    conn.close()
    logger.info("Closer Agent done.")


if __name__ == "__main__":
    run()
