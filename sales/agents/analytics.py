"""VetFlow Sales — Analytics Agent

Generates a daily sales-pipeline report from vetflow_sales.db and
saves it to vetflow_sales/reports/daily_YYYY-MM-DD.txt.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [analytics] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("analytics")

# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH      = ROOT / "data" / "vetflow_sales.db"
REPORTS_DIR  = ROOT / "vetflow_sales" / "reports"
SETUP_FEE    = 1_997.0
MONTHLY_FEE  = 497.0
CLOSE_RATE   = 0.20   # 20 % assumed close rate for pipeline value


# ── Database helpers ──────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> float:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return 0
    return row[0] or 0


# ── Query helpers ─────────────────────────────────────────────────────────────
def pipeline_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM clinics GROUP BY status"
    ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}


def touchpoints_today(conn: sqlite3.Connection) -> dict:
    today = date.today().isoformat()
    channels = {}
    for channel in ("email", "sms", "call"):
        channels[channel] = scalar(
            conn,
            "SELECT COUNT(*) FROM touchpoints WHERE channel=? AND DATE(sent_at)=? AND direction='outbound' AND status != 'queued'",
            (channel, today),
        )
    # Calgary calls specifically (all calls in vetflow_sales.db are Calgary)
    channels["calls_placed"] = channels["call"]
    channels["sms_queued"]   = scalar(
        conn,
        "SELECT COUNT(*) FROM touchpoints WHERE channel='sms' AND status='queued'",
    )
    return channels


def touchpoints_this_week(conn: sqlite3.Connection) -> int:
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    return scalar(
        conn,
        "SELECT COUNT(*) FROM touchpoints WHERE direction='outbound' AND DATE(sent_at) >= ?",
        (week_start,),
    )


def touchpoints_all_time(conn: sqlite3.Connection) -> int:
    return scalar(
        conn,
        "SELECT COUNT(*) FROM touchpoints WHERE direction='outbound' AND sent_at IS NOT NULL",
    )


def reply_stats(conn: sqlite3.Connection) -> dict:
    total_sent    = touchpoints_all_time(conn) or 1
    total_replies = scalar(conn, "SELECT COUNT(*) FROM replies")
    interested    = scalar(conn, "SELECT COUNT(*) FROM replies WHERE classification='interested'")
    curious       = scalar(conn, "SELECT COUNT(*) FROM replies WHERE classification='curious'")
    positive      = interested + curious
    reply_rate    = (total_replies / total_sent) * 100
    positive_rate = (positive / max(total_replies, 1)) * 100
    return {
        "total_replies":  total_replies,
        "interested":     interested,
        "curious":        curious,
        "positive":       positive,
        "reply_rate":     reply_rate,
        "positive_rate":  positive_rate,
    }


def calls_booked(conn: sqlite3.Connection) -> int:
    return scalar(conn, "SELECT COUNT(*) FROM bookings WHERE status != 'cancelled'")


def deals_closed(conn: sqlite3.Connection) -> dict:
    closed = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status='closed'")
    mrr    = closed * MONTHLY_FEE
    return {"closed": closed, "mrr": mrr}


def pipeline_value(conn: sqlite3.Connection) -> float:
    interested = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status='interested'")
    return interested * SETUP_FEE * CLOSE_RATE


def clinics_needing_followup(conn: sqlite3.Connection) -> int:
    """Clinics contacted on day 1 that are due for day-3 followup (2+ days ago)."""
    cutoff = (date.today() - timedelta(days=2)).isoformat()
    return scalar(
        conn,
        """SELECT COUNT(DISTINCT t.clinic_id) FROM touchpoints t
           WHERE t.sequence_day=1
             AND t.direction='outbound'
             AND DATE(t.sent_at) <= ?
             AND NOT EXISTS (
                 SELECT 1 FROM touchpoints t2
                 WHERE t2.clinic_id = t.clinic_id AND t2.sequence_day=3
             )""",
        (cutoff,),
    )


def hot_leads_needing_response(conn: sqlite3.Connection) -> int:
    return scalar(
        conn,
        "SELECT COUNT(*) FROM replies WHERE classification IN ('interested','curious') AND handled=0",
    )


def proof_page_views(conn: sqlite3.Connection) -> int:
    """Total proof page views recorded in the Railway demo_pages table (if synced)."""
    try:
        return scalar(conn, "SELECT SUM(views) FROM demo_pages")
    except Exception:
        return 0


def weekly_stats(conn: sqlite3.Connection) -> dict:
    """Activity summary for the past 7 days."""
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    calls  = scalar(conn,
        "SELECT COUNT(*) FROM touchpoints WHERE channel='call' AND DATE(sent_at)>=? AND status NOT IN ('error','failed','queued')",
        (week_ago,))
    emails = scalar(conn,
        "SELECT COUNT(*) FROM touchpoints WHERE channel='email' AND DATE(sent_at)>=? AND status='sent'",
        (week_ago,))
    sms    = scalar(conn,
        "SELECT COUNT(*) FROM touchpoints WHERE channel='sms' AND DATE(sent_at)>=? AND status='sent'",
        (week_ago,))
    replies_w = scalar(conn,
        "SELECT COUNT(*) FROM replies WHERE DATE(received_at)>=?", (week_ago,))
    interested_w = scalar(conn,
        "SELECT COUNT(*) FROM replies WHERE classification='interested' AND DATE(received_at)>=?", (week_ago,))
    curious_w = scalar(conn,
        "SELECT COUNT(*) FROM replies WHERE classification='curious' AND DATE(received_at)>=?", (week_ago,))
    new_clinics_w = scalar(conn,
        "SELECT COUNT(*) FROM clinics WHERE DATE(updated_at)>=? AND status='contacted'", (week_ago,))
    return {
        "calls": calls, "emails": emails, "sms": sms,
        "replies": replies_w, "interested": interested_w,
        "curious": curious_w, "new_contacted": new_clinics_w,
    }


def clinics_to_score(conn: sqlite3.Connection) -> int:
    return scalar(
        conn,
        "SELECT COUNT(*) FROM clinics WHERE score=0 OR score IS NULL",
    )


def top_untouched_clinic(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """SELECT c.name FROM clinics c
           WHERE c.status='new'
             AND NOT EXISTS (
                 SELECT 1 FROM touchpoints t WHERE t.clinic_id = c.id
             )
           ORDER BY c.score DESC
           LIMIT 1"""
    ).fetchone()
    return row["name"] if row else "None"


def top5_uncontacted(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT name, score, email FROM clinics
           WHERE status='new' AND (email IS NOT NULL AND email != '')
             AND NOT EXISTS (
                 SELECT 1 FROM touchpoints t WHERE t.clinic_id = clinics.id
             )
           ORDER BY score DESC
           LIMIT 5"""
    ).fetchall()
    return [dict(r) for r in rows]


# ── Report builder ─────────────────────────────────────────────────────────────
def build_report(conn: sqlite3.Connection) -> str:
    today_str  = datetime.now().strftime("%B %d, %Y")
    pipeline   = pipeline_by_status(conn)
    tp_today   = touchpoints_today(conn)
    tp_week    = touchpoints_this_week(conn)
    tp_all     = touchpoints_all_time(conn)
    r_stats    = reply_stats(conn)
    booked     = calls_booked(conn)
    deals      = deals_closed(conn)
    p_value    = pipeline_value(conn)
    followups  = clinics_needing_followup(conn)
    hot        = hot_leads_needing_response(conn)
    to_score   = clinics_to_score(conn)
    top_clinic = top_untouched_clinic(conn)
    top5       = top5_uncontacted(conn)
    w_stats    = weekly_stats(conn)
    proof_views = proof_page_views(conn)

    # Derived numbers
    new_leads    = pipeline.get("new", 0)
    contacted    = pipeline.get("contacted", 0)
    replied      = pipeline.get("replied", 0)
    interested   = pipeline.get("interested", 0)
    booked_cnt   = pipeline.get("booked", booked)
    closed       = pipeline.get("closed", deals["closed"])

    total_emails_all = tp_all or 1
    email_open_rate  = 0.0   # tracked via SendGrid webhooks; placeholder
    call_booked_rate = (booked / max(r_stats["interested"], 1)) * 100

    mrr      = deals["mrr"]
    p_value_adj = p_value  # already at 20 % close

    tier_a_untouched = scalar(conn,
        "SELECT COUNT(*) FROM clinics WHERE score >= 75 AND status = 'new'"
    )
    calls_total  = scalar(conn,
        "SELECT COUNT(*) FROM touchpoints WHERE channel='call' AND status != 'error'"
    )
    sms_queued   = tp_today.get("sms_queued", 0)

    lines = [
        "=" * 50,
        "  VETFLOW SALES — DAILY REPORT",
        f"  {today_str}",
        "=" * 50,
        "",
        "CALGARY PIPELINE (28 clinics)",
        f"  New (not contacted):  {new_leads:>4}",
        f"  Contacted:            {contacted:>4}",
        f"  Replied:              {replied:>4}",
        f"  Interested:           {interested:>4}  ← MONEY HERE",
        f"  Booked:               {booked_cnt:>4}",
        f"  Closed:               {closed:>4}",
        f"  Tier A untouched:     {tier_a_untouched:>4}  (score 75+)",
        "",
        "TODAY — OUTREACH",
        f"  Calls placed:         {tp_today['calls_placed']:>4}  (Calgary vet clinics)",
        f"  SMS sent:             {tp_today['sms']:>4}  | queued: {sms_queued}",
        f"  Emails sent:          {tp_today['email']:>4}",
        "",
        "ALL TIME",
        f"  Total calls placed:   {calls_total:>4}",
        f"  Total touchpoints:    {tp_all:>4}",
        "",
        "REPLIES & CONVERSION",
        f"  Total replies:        {r_stats['total_replies']:>4}",
        f"  Interested:           {r_stats['interested']:>4}",
        f"  Curious:              {r_stats['curious']:>4}",
        f"  Positive total:       {r_stats['positive']:>4}",
        f"  Reply rate:           {r_stats['reply_rate']:>5.1f}%",
        f"  Positive rate:        {r_stats['positive_rate']:>5.1f}%",
        f"  Demos booked:         {booked_cnt:>4}",
        "",
        "REVENUE",
        f"  Pipeline value:       ${p_value_adj:>7,.0f}  (at {int(CLOSE_RATE*100)}% close)",
        f"  Deals closed:         {closed}",
        f"  MRR:                 ${mrr:>7,.0f}/mo",
        "",
        "NEXT ACTIONS",
        f"  → {tier_a_untouched} Tier A clinics not yet called (call these FIRST)",
        f"  → {followups} clinics ready for Day-3 followup",
        f"  → {hot} hot leads need manual response",
        f"  → Top untouched: {top_clinic}",
    ]

    lines += [
        "",
        "LAST 7 DAYS",
        f"  Calls:                {w_stats['calls']:>4}",
        f"  Emails:               {w_stats['emails']:>4}",
        f"  SMS:                  {w_stats['sms']:>4}",
        f"  Replies:              {w_stats['replies']:>4}",
        f"  Interested:           {w_stats['interested']:>4}",
        f"  Curious:              {w_stats['curious']:>4}",
        f"  New contacts:         {w_stats['new_contacted']:>4}",
        f"  Proof page views:     {proof_views:>4}",
    ]

    if top5:
        lines.append("")
        lines.append("TOP 5 UNCONTACTED (by score)")
        for i, c in enumerate(top5, 1):
            lines.append(f"  {i}. {c['name']} — score {c['score']} — {c.get('email','no email')}")

    lines.append("=" * 40)
    return "\n".join(lines)


# ── Save to file ───────────────────────────────────────────────────────────────
def save_report(report: str):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fname = REPORTS_DIR / f"daily_{date.today().isoformat()}.txt"
    fname.write_text(report, encoding="utf-8")
    log.info(f"Report saved → {fname}")
    return fname


# ── Main ───────────────────────────────────────────────────────────────────────
def run() -> str:
    log.info("Analytics agent starting...")

    if not DB_PATH.exists():
        log.warning(f"Database not found at {DB_PATH} — report will show zeros.")
        # Create empty DB with schema so script doesn't crash
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        schema_path = ROOT / "vetflow_sales" / "schema.sql"
        conn = sqlite3.connect(str(DB_PATH))
        if schema_path.exists():
            conn.executescript(schema_path.read_text())
            conn.commit()
        conn.close()

    conn = get_db()
    try:
        report = build_report(conn)
    finally:
        conn.close()

    print(report)
    saved = save_report(report)
    print(f"\nReport saved to: {saved}")
    return report


if __name__ == "__main__":
    run()
