#!/usr/bin/env python3
"""Sequence Runner — sends Day 1/3/5/7 outreach to Calgary vet clinics."""

import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

from vetflow_sales.agents.coordinator import Coordinator

DB_PATH = PROJECT_ROOT / "data" / "vetflow_sales.db"
TEMPLATE_DIR = PROJECT_ROOT / "vetflow_sales" / "templates"
CALENDLY_LINK = "https://calendly.com/vetflow-ai/15-min-discovery-call"
DEMO_LINK = "https://vetflow-ai-production.up.railway.app"
FROM_EMAIL = "vetflow.ai@gmail.com"
FROM_NAME = "Karan at VetFlow AI"
MAX_PER_RUN = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vetflow.sequence_runner")


def load_template(name: str) -> str:
    path = TEMPLATE_DIR / name
    if path.exists():
        return path.read_text()
    return ""


def fill_template(template: str, clinic: sqlite3.Row, day: int) -> tuple:
    """Returns (subject, body) after filling template variables."""
    lines = template.strip().split("\n")
    subject = ""
    body_lines = []
    for i, line in enumerate(lines):
        if line.startswith("SUBJECT:"):
            subject = line.replace("SUBJECT:", "").strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()

    name = clinic["name"]
    insight = clinic["ai_insight"] if clinic["ai_insight"] else ""
    missed_rev = clinic["missed_revenue_estimate"] if clinic["missed_revenue_estimate"] else "$3,000–6,000/month"

    for k, v in [
        ("{{clinic_name}}", name),
        ("{{owner_name_or_team}}", "team"),
        ("{{insight}}", insight),
        ("{{calendly_link}}", CALENDLY_LINK),
        ("{{demo_link}}", DEMO_LINK),
        ("{{missed_revenue_estimate}}", missed_rev),
        ("{{city}}", "Calgary"),
    ]:
        subject = subject.replace(k, v)
        body = body.replace(k, v)

    return subject, body


def send_email(to_email: str, subject: str, body: str) -> Optional[str]:
    """Send via SendGrid. Returns message_id or None on failure."""
    api_key = os.getenv("SENDGRID_API_KEY", "")
    if not api_key:
        logger.error("No SENDGRID_API_KEY in env")
        return None
    try:
        sg = SendGridAPIClient(api_key)
        msg = Mail()
        msg.from_email = Email(FROM_EMAIL, FROM_NAME)
        msg.to = To(to_email)
        msg.subject = subject
        msg.content = [Content("text/plain", body)]
        resp = sg.send(msg)
        if resp.status_code in (200, 201, 202):
            msg_id = resp.headers.get("X-Message-Id", "")
            logger.info("  Email sent → %s (status %d)", to_email, resp.status_code)
            return msg_id
        else:
            logger.error("  SendGrid %d: %s", resp.status_code, resp.body)
            return None
    except Exception as e:
        logger.error("  SendGrid error: %s", e)
        return None


def get_clinics_for_day1(conn: sqlite3.Connection, limit: int):
    return conn.execute(
        """SELECT c.*, NULL as ai_insight, NULL as missed_revenue_estimate
           FROM clinics c
           WHERE c.status = 'new'
             AND c.score >= 40
             AND c.email IS NOT NULL AND c.email != ''
             AND NOT EXISTS (
                 SELECT 1 FROM touchpoints t WHERE t.clinic_id = c.id AND t.status = 'sent'
             )
           ORDER BY c.score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()


def get_clinics_for_followup(conn: sqlite3.Connection, day: int, limit: int):
    cutoff = (datetime.now() - timedelta(days=day - 1)).isoformat()
    return conn.execute(
        """SELECT c.*, NULL as ai_insight, NULL as missed_revenue_estimate
           FROM clinics c
           WHERE c.status = 'contacted'
             AND c.email IS NOT NULL AND c.email != ''
             AND NOT EXISTS (
                 SELECT 1 FROM touchpoints t
                 WHERE t.clinic_id = c.id
                   AND t.sequence_day = ?
                   AND t.status = 'sent'
             )
             AND EXISTS (
                 SELECT 1 FROM touchpoints t
                 WHERE t.clinic_id = c.id
                   AND t.sequence_day = ?
                   AND t.sent_at <= ?
                   AND t.status = 'sent'
             )
           ORDER BY c.score DESC
           LIMIT ?""",
        (day, day - 2 if day > 1 else 1, cutoff, limit),
    ).fetchall()


def record_touchpoint(conn: sqlite3.Connection, clinic_id: int, email: str,
                      subject: str, body: str, day: int, msg_id: Optional[str]) -> None:
    conn.execute(
        """INSERT INTO touchpoints
           (clinic_id, channel, sequence_day, subject, body, sent_at, status)
           VALUES (?, 'email', ?, ?, ?, ?, ?)""",
        (clinic_id, day, subject, body, datetime.now().isoformat(),
         "sent" if msg_id is not None else "failed"),
    )


def run() -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    coordinator = Coordinator(conn)

    # Also load ai_insight/missed_revenue_estimate if columns exist
    try:
        conn.execute("SELECT ai_insight FROM clinics LIMIT 1")
        has_insight = True
    except sqlite3.OperationalError:
        has_insight = False

    sent = 0
    failed = 0
    skipped = 0

    # Add insight columns if missing
    if not has_insight:
        try:
            conn.execute("ALTER TABLE clinics ADD COLUMN ai_insight TEXT")
            conn.execute("ALTER TABLE clinics ADD COLUMN missed_revenue_estimate TEXT")
            conn.commit()
        except Exception:
            pass

    sequence = [
        (1, "email_day1.txt", get_clinics_for_day1),
    ]

    for day, template_file, getter in sequence:
        template = load_template(template_file)
        if not template:
            logger.warning("Template not found: %s", template_file)
            continue

        remaining = MAX_PER_RUN - sent
        if remaining <= 0:
            break

        if day == 1:
            clinics = getter(conn, remaining)
        else:
            clinics = getter(conn, day, remaining)

        logger.info("Day %d: %d clinics ready", day, len(clinics))

        for clinic in clinics:
            email = clinic["email"]

            # ── Coordinator safety gate ───────────────────────────────────
            ok, reason = coordinator.safe_to_email(dict(clinic), day)
            if not ok:
                logger.info("SKIP Day %d | %-40s reason: %s", day, clinic["name"], reason)
                skipped += 1
                continue

            subject, body = fill_template(template, clinic, day)

            if not subject or not body:
                logger.warning("Empty template output for %s", clinic["name"])
                continue

            logger.info("Sending Day %d to %s <%s>", day, clinic["name"], email)
            msg_id = send_email(email, subject, body)

            record_touchpoint(conn, clinic["id"], email, subject, body, day, msg_id)

            if msg_id:
                conn.execute(
                    "UPDATE clinics SET status='contacted', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (clinic["id"],),
                )
                sent += 1
            else:
                failed += 1

            conn.commit()

    # Also process followup days 3, 5, 7
    for day, template_file in [(3, "email_day3.txt"), (5, "email_day5.txt"), (7, "email_day7.txt")]:
        template = load_template(template_file)
        if not template:
            continue
        remaining = MAX_PER_RUN - sent
        if remaining <= 0:
            break
        clinics = get_clinics_for_followup(conn, day, remaining)
        logger.info("Followup Day %d: %d clinics ready", day, len(clinics))
        for clinic in clinics:
            email = clinic["email"]

            # ── Coordinator safety gate ───────────────────────────────────
            ok, reason = coordinator.safe_to_email(dict(clinic), day)
            if not ok:
                logger.info("SKIP Day %d | %-40s reason: %s", day, clinic["name"], reason)
                skipped += 1
                continue

            subject, body = fill_template(template, clinic, day)
            msg_id = send_email(email, subject, body)
            record_touchpoint(conn, clinic["id"], email, subject, body, day, msg_id)
            if msg_id:
                sent += 1
            else:
                failed += 1
            conn.commit()

    conn.close()
    logger.info("Sequence runner done: %d sent, %d failed, %d skipped", sent, failed, skipped)
    return {"sent": sent, "failed": failed, "skipped": skipped}


if __name__ == "__main__":
    result = run()
    print(f"\nResult: {result['sent']} sent, {result['failed']} failed")
