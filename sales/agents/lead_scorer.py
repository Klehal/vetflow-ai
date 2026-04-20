"""Lead Scorer Agent — scores Calgary vet clinics 0-100 for sales priority."""

import logging
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: load .env and add project root to sys.path
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = PROJECT_ROOT / "data" / "vetflow_sales.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("vetflow.lead_scorer")


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

CHAIN_NAMES    = ["vca ", "vca canada", "banfield", "petsmart", "petco"]
EMERGENCY_KEYS = ["24 hour", "24/7", "24hr", "emergency", "urgent care"]
SPECIALIST_KEYS = ["specialist", "referral", "oncology", "cardiology", "neurology",
                   "ophthalmology", "dermatology", "internal medicine"]


def classify_clinic(name: str) -> tuple:
    """Return (clinic_type, fit_penalty, fit_note)."""
    n = name.lower()
    if any(k in n for k in CHAIN_NAMES):
        return "chain", -25, "chain clinic — corporate buying decision, hard to close locally"
    if any(k in n for k in SPECIALIST_KEYS) and "emergency" not in n:
        return "specialist", -20, "specialist/referral — different intake model, lower fit"
    if any(k in n for k in EMERGENCY_KEYS):
        return "emergency_24hr", -10, "24hr/emergency — may have overflow processes, harder sell"
    return "general", 0, ""


def score_clinic(row: sqlite3.Row) -> tuple:
    """
    Return (score 0-100, notes) for a clinic row.

    Higher score = higher sales priority (more pain points we can solve).
    """
    score = 0
    reasons = []

    has_website  = bool(row["has_website"])
    quality      = row["website_quality_score"] or 0
    has_booking  = bool(row["has_online_booking"])
    rating       = row["google_rating"]
    review_count = row["review_count"] or 0
    after_hours_gap = bool(row["after_hours_gap"])
    phone        = row["phone"]
    name         = row["name"] or ""

    # Qualification — classify and apply fit penalty
    clinic_type, fit_penalty, fit_note = classify_clinic(name)
    if fit_penalty:
        score += fit_penalty   # negative
        reasons.append(fit_note)

    # ------------------------------------------------------------------
    # Core: Established clinic = can afford $497/mo AND has busy phones
    # VetFlow works for ALL clinics — even ones with websites/booking
    # still miss calls during lunch, evenings, weekends
    # ------------------------------------------------------------------
    if rating is not None and rating >= 4.0 and review_count >= 50:
        score += 30
        reasons.append(f"established busy clinic ({rating:.1f}★, {review_count} reviews)")
    elif rating is not None and rating >= 3.5 and review_count >= 20:
        score += 15
        reasons.append(f"growing clinic ({rating:.1f}★, {review_count} reviews)")

    # More reviews = busier phones = more missed calls = higher ROI
    if review_count >= 200:
        score += 20
        reasons.append(f"high volume ({review_count} reviews = very busy)")
    elif review_count >= 100:
        score += 10
        reasons.append(f"solid volume ({review_count} reviews)")

    # ------------------------------------------------------------------
    # No online booking = missed appointments on top of missed calls
    # ------------------------------------------------------------------
    if not has_booking:
        score += 20
        reasons.append("no online booking system — losing appointments 24/7")

    # ------------------------------------------------------------------
    # Website signals — no/poor website = more pain, easier sell
    # ------------------------------------------------------------------
    if not has_website:
        score += 15
        reasons.append("no website — highly underserved")
    elif quality <= 3:
        score += 10
        reasons.append(f"poor website (quality {quality}/10)")

    # ------------------------------------------------------------------
    # After-hours gap = guaranteed missed calls every evening/weekend
    # ------------------------------------------------------------------
    if after_hours_gap:
        score += 15
        reasons.append("closed evenings/weekends — every after-hours call is missed")

    # ------------------------------------------------------------------
    # Contact reachability
    # ------------------------------------------------------------------
    if phone:
        score += 5
        reasons.append("phone available for call outreach")

    # Cap at 100
    score = min(100, score)

    if not reasons:
        notes = "No strong pain-point signals — lower priority."
    else:
        notes = "Good target: " + ", ".join(reasons) + "."

    return score, notes


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_unscored_clinics(conn: sqlite3.Connection) -> list:
    return conn.execute(
        "SELECT * FROM clinics WHERE score = 0 OR score IS NULL"
    ).fetchall()


def reclassify_all(conn: sqlite3.Connection):
    """Update clinic_type for all clinics (run once after schema change)."""
    rows = conn.execute("SELECT id, name FROM clinics").fetchall()
    for r in rows:
        clinic_type, _, _ = classify_clinic(r["name"] or "")
        conn.execute(
            "UPDATE clinics SET clinic_type=? WHERE id=?",
            (clinic_type, r["id"]),
        )
    conn.commit()
    logger.info("Reclassified %d clinics.", len(rows))


def update_score(
    conn: sqlite3.Connection, clinic_id: int, score: int, notes: str
) -> None:
    conn.execute(
        """
        UPDATE clinics
        SET score = ?, score_notes = ?,
            clinic_type = (SELECT clinic_type FROM clinics WHERE id = ?),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (score, notes, clinic_id, clinic_id),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> dict:
    """Score all unscored clinics. Returns a summary dict."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Always reclassify types (fast, idempotent)
    reclassify_all(conn)

    clinics = get_unscored_clinics(conn)
    logger.info("Scoring %d unscored clinics …", len(clinics))

    scored = 0
    buckets = {"high (70-100)": 0, "medium (40-69)": 0, "low (0-39)": 0}

    for clinic in clinics:
        score, notes = score_clinic(clinic)
        update_score(conn, clinic["id"], score, notes)
        scored += 1

        if score >= 70:
            buckets["high (70-100)"] += 1
        elif score >= 40:
            buckets["medium (40-69)"] += 1
        else:
            buckets["low (0-39)"] += 1

        logger.info("  [%3d] %s — %s", score, clinic["name"], notes)

    conn.commit()
    conn.close()

    logger.info("Scorer complete. Scored: %d", scored)
    return {"scored": scored, "buckets": buckets}


if __name__ == "__main__":
    summary = run()
    print(f"\nScored {summary['scored']} clinics:")
    for bucket, count in summary["buckets"].items():
        print(f"  {bucket}: {count}")
