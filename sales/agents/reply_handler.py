"""VetFlow Sales — Reply Handler Agent

Checks Gmail for inbound replies, classifies them with GPT-4o-mini,
updates clinic status, generates responses for hot leads, and logs to
hot_leads.txt.
"""

import os
import sys
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [reply_handler] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reply_handler")

# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH         = ROOT / "data" / "vetflow_sales.db"
HOT_LEADS_FILE  = ROOT / "vetflow_sales" / "hot_leads.txt"
CALENDLY_LINK   = "https://calendly.com/vetflow-ai/15-min-discovery-call"
GMAIL_SEARCH    = "to:vetflow.ai@gmail.com newer_than:1d"

STATUS_MAP = {
    "interested":           "interested",
    "curious":              "contacted",          # keep in pipeline, follow up
    "not_now":              "nurture",
    "wrong_person":         "contacted",          # re-route, don't remove
    "already_have_process": "nurture",            # has a solution; check in 6 months
    "unsubscribe":          "dead",
}

# ── OpenAI client (lazy import so the file still loads without the package) ───
def _openai_client():
    try:
        from openai import OpenAI
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except ImportError:
        log.error("openai package not installed — pip install openai")
        return None


# ── Database helpers ──────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def find_clinic_by_email(conn: sqlite3.Connection, email: str) -> dict:
    row = conn.execute(
        "SELECT * FROM clinics WHERE lower(email) = lower(?)", (email,)
    ).fetchone()
    return dict(row) if row else None


def save_reply(
    conn: sqlite3.Connection,
    clinic_id: int,
    body: str,
    classification: str,
    ai_response,
    channel: str = "email",
) -> int:
    cursor = conn.execute(
        """INSERT INTO replies (clinic_id, channel, body, received_at,
                                classification, ai_response, handled)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (clinic_id, channel, body, datetime.now().isoformat(),
         classification, ai_response),
    )
    conn.commit()
    return cursor.lastrowid


def update_clinic_status(conn: sqlite3.Connection, clinic_id: int, status: str):
    conn.execute(
        "UPDATE clinics SET status = ?, updated_at = ? WHERE id = ?",
        (status, datetime.now().isoformat(), clinic_id),
    )
    conn.commit()


# ── GPT helpers ───────────────────────────────────────────────────────────────
def classify_reply(client, reply_text: str) -> dict:
    """Return {classification, confidence, summary} from GPT-4o-mini."""
    prompt = (
        "Classify this email reply from a vet clinic owner or staff member. "
        f"Reply: {reply_text}\n\n"
        "Classifications:\n"
        "- interested: actively wants to know more or book a call\n"
        "- curious: asking a question or showing mild interest\n"
        "- objection: has a specific reason they can't use it right now\n"
        "- not_now: busy, not the right time, but not hostile\n"
        "- already_have_process: explicitly says they already have a system/solution for missed calls\n"
        "- wrong_person: forwarded or replied saying they're not the decision maker\n"
        "- unsubscribe: wants to be removed, stop contact\n"
        "- out_of_office: auto-reply\n"
        "- unknown: unclear\n\n"
        "Return JSON: {\"classification\": \"<one of above>\", "
        "\"confidence\": 0.0-1.0, \"summary\": \"one sentence\"}"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:
        log.warning(f"GPT classification failed: {exc}")
        return {"classification": "unknown", "confidence": 0.0, "summary": str(exc)}


def generate_response(client, reply_text: str, clinic_name: str, classification: str = "interested") -> str:
    """Generate a contextual reply based on classification."""
    if classification == "interested":
        prompt = (
            f"Write a SHORT, warm reply to this vet clinic owner who's interested in VetFlow AI. "
            f"Under 4 sentences. Be direct — give them the booking link immediately. "
            f"Don't oversell. Sound like a real person.\n"
            f"Booking link: {CALENDLY_LINK}\n\n"
            f"Clinic: {clinic_name}\nTheir reply: {reply_text}\n\n"
            f"Start your reply with 'Great!' or similar, give the link, end warmly."
        )
    elif classification == "curious":
        prompt = (
            f"Write a SHORT reply to this vet clinic owner who is asking a question or seems curious. "
            f"Under 4 sentences. Answer their question briefly, then ask ONE follow-up question "
            f"to understand their situation better. Do NOT give the booking link yet — build rapport first.\n\n"
            f"Clinic: {clinic_name}\nTheir reply: {reply_text}"
        )
    elif classification == "objection":
        prompt = (
            f"Write a SHORT reply to this vet clinic owner who has an objection. "
            f"Under 4 sentences. Acknowledge their concern genuinely, reframe briefly, "
            f"and ask if it's worth 15 minutes to see if it applies to them.\n"
            f"Booking link: {CALENDLY_LINK}\n\n"
            f"Clinic: {clinic_name}\nTheir reply: {reply_text}"
        )
    elif classification == "already_have_process":
        prompt = (
            f"Write a SHORT, gracious reply to this vet clinic owner who says they already "
            f"have a system handling missed calls. Under 3 sentences. "
            f"Acknowledge that's great, say something genuine and positive, "
            f"and leave a friendly door open — nothing pushy. No sales pitch. No link.\n\n"
            f"Clinic: {clinic_name}\nTheir reply: {reply_text}"
        )
    else:
        return ""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        log.warning(f"GPT response generation failed: {exc}")
        return (
            f"Thanks so much for your interest! I'd love to connect and show you exactly "
            f"how VetFlow AI can help {clinic_name}. You can grab a time that works for you "
            f"here: {CALENDLY_LINK} — looking forward to chatting soon!"
        )


# ── Hot leads file ─────────────────────────────────────────────────────────────
def append_hot_lead(clinic_name: str, email: str, snippet: str, ai_response: str):
    HOT_LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n{'─' * 60}\n"
        f"Date:      {today}\n"
        f"Clinic:    {clinic_name}\n"
        f"Email:     {email}\n"
        f"Status:    INTERESTED\n"
        f"Reply:     {snippet[:200]}\n"
        f"Response:  {ai_response}\n"
    )
    with open(HOT_LEADS_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry)
    log.info(f"Hot lead saved to {HOT_LEADS_FILE}")


# ── Gmail fetch via MCP ────────────────────────────────────────────────────────
def fetch_gmail_replies() -> list[dict]:
    """
    Fetch recent inbound reply threads from Gmail using the MCP Gmail tools.

    In production this is called by the Claude agent harness which injects
    the mcp__*__search_threads / get_thread tools. When run standalone we
    fall back to a local stub so the script remains importable and testable.

    Returns a list of dicts with keys: from_email, subject, body, thread_id.
    """
    # The actual MCP calls are issued at runtime by the agent harness; this
    # function provides the interface contract and a graceful fallback.
    log.info(f"Searching Gmail: '{GMAIL_SEARCH}'")
    log.info(
        "NOTE: Gmail MCP calls (search_threads / get_thread) are injected "
        "at runtime by the Claude agent harness. In standalone mode this "
        "function returns an empty list."
    )
    return []


# ── MCP-aware entry point (called by agent harness) ──────────────────────────
def process_email_messages(messages: list[dict]) -> list[dict]:
    """
    Core processing logic — separated so the agent harness can pass real
    Gmail messages without going through fetch_gmail_replies().

    Each message dict must have: from_email, subject, body, thread_id (optional).
    Returns list of processed result dicts.
    """
    client = _openai_client()
    conn = get_db()
    hot_leads: list[dict] = []
    results: list[dict] = []

    for msg in messages:
        from_email = msg.get("from_email", "").strip().lower()
        body       = msg.get("body", "")
        subject    = msg.get("subject", "")

        if not from_email or not body:
            log.debug("Skipping message with missing from_email or body")
            continue

        # ── Match clinic ──────────────────────────────────────────────────
        clinic = find_clinic_by_email(conn, from_email)
        if not clinic:
            log.info(f"No clinic matched for {from_email} — skipping")
            continue

        clinic_id   = clinic["id"]
        clinic_name = clinic["name"]

        # ── Classify ──────────────────────────────────────────────────────
        classification_result = classify_reply(client, body) if client else {
            "classification": "unknown", "confidence": 0.0, "summary": "no client"
        }
        classification = classification_result.get("classification", "unknown")
        confidence     = classification_result.get("confidence", 0.0)
        summary        = classification_result.get("summary", "")

        log.info(
            f"[{clinic_name}] {from_email} → {classification.upper()} "
            f"(conf={confidence:.2f}) | {summary}"
        )

        # ── Generate response for actionable leads ────────────────────────
        ai_response = None
        if classification in ("interested", "curious", "objection", "already_have_process"):
            ai_response = generate_response(client, body, clinic_name, classification) if client else (
                f"Thanks for getting back to me! Here's a link to grab a time: {CALENDLY_LINK}"
            )

        # ── Save reply ────────────────────────────────────────────────────
        save_reply(conn, clinic_id, body, classification, ai_response)

        # ── Update clinic status ──────────────────────────────────────────
        new_status = STATUS_MAP.get(classification)
        if new_status:
            update_clinic_status(conn, clinic_id, new_status)
            log.info(f"  → Clinic status updated to '{new_status}'")

        # ── Hot lead alert ────────────────────────────────────────────────
        if classification in ("interested", "curious"):
            snippet = body[:120].replace("\n", " ")
            print(
                f"\n{'='*60}\n"
                f"  HOT LEAD: {clinic_name} replied INTERESTED\n"
                f"  Email:    {from_email}\n"
                f"  Snippet:  {snippet}...\n"
                f"{'='*60}"
            )
            hot_leads.append({
                "clinic_name": clinic_name,
                "email":       from_email,
                "snippet":     snippet,
                "ai_response": ai_response,
            })
            append_hot_lead(clinic_name, from_email, snippet, ai_response)

        results.append({
            "clinic_id":      clinic_id,
            "clinic_name":    clinic_name,
            "email":          from_email,
            "classification": classification,
            "confidence":     confidence,
            "summary":        summary,
            "ai_response":    ai_response,
        })

    conn.close()

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n[reply_handler] Processed {len(results)} replies.")
    if hot_leads:
        print(f"[reply_handler] {len(hot_leads)} HOT LEAD(S) detected — see {HOT_LEADS_FILE}")
    else:
        print("[reply_handler] No interested leads this run.")

    return results


# ── Standalone runner ─────────────────────────────────────────────────────────
def run():
    """Entry point when called directly or from run_daily.py."""
    log.info("Reply Handler starting...")

    # Fetch messages (no-op in standalone; MCP harness provides real data)
    messages = fetch_gmail_replies()

    if not messages:
        log.info("No new messages to process (standalone / no MCP context).")
        return []

    return process_email_messages(messages)


if __name__ == "__main__":
    run()
