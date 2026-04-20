#!/usr/bin/env python3
"""Coordinator — shared safety layer for all VetFlow agents.

Provides:
  - Cooldown enforcement (no clinic contacted twice within X days per channel)
  - Duplicate prevention (idempotent touchpoint checking)
  - Pipeline state validation (agents can check "am I safe to run?")
  - Tier routing (A/B/C)

Import this in any agent that touches clinics:
    from vetflow_sales.agents.coordinator import Coordinator
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "vetflow_sales.db"

# ── Cooldown windows per channel (days) ──────────────────────────────────────
COOLDOWNS = {
    "call":  3,   # don't call same clinic within 3 days
    "sms":   2,   # don't SMS within 2 days
    "email": 2,   # don't email within 2 days
}

# ── Tier thresholds ───────────────────────────────────────────────────────────
TIER_A = 75
TIER_B = 40   # minimum for any outreach
# Below TIER_B → Tier C → hold, do not contact


class Coordinator:
    def __init__(self, conn: sqlite3.Connection = None):
        if conn is None:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
        self.conn = conn

    # ── Tier helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def tier(score: int) -> str:
        if score >= TIER_A:
            return "A"
        if score >= TIER_B:
            return "B"
        return "C"

    @staticmethod
    def is_contactable(score: int) -> bool:
        return score >= TIER_B

    # ── Cooldown checks ───────────────────────────────────────────────────────

    def on_cooldown(self, clinic_id: int, channel: str) -> bool:
        """Return True if this clinic was contacted via channel within cooldown window."""
        days = COOLDOWNS.get(channel, 2)
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        row = self.conn.execute(
            """SELECT 1 FROM touchpoints
               WHERE clinic_id=? AND channel=? AND direction='outbound'
                 AND status NOT IN ('failed','error','queued')
                 AND sent_at >= ?
               LIMIT 1""",
            (clinic_id, channel, cutoff),
        ).fetchone()
        return row is not None

    def already_called(self, clinic_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM touchpoints WHERE clinic_id=? AND channel='call' LIMIT 1",
            (clinic_id,),
        ).fetchone()
        return row is not None

    def already_emailed_day(self, clinic_id: int, day: int) -> bool:
        row = self.conn.execute(
            """SELECT 1 FROM touchpoints
               WHERE clinic_id=? AND channel='email'
                 AND sequence_day=? AND status='sent' LIMIT 1""",
            (clinic_id, day),
        ).fetchone()
        return row is not None

    def has_proof_page(self, clinic_id: int) -> bool:
        row = self.conn.execute(
            "SELECT proof_page_url FROM clinics WHERE id=?", (clinic_id,)
        ).fetchone()
        return bool(row and row[0] and row[0].startswith("http"))

    def is_dead(self, clinic_id: int) -> bool:
        row = self.conn.execute(
            "SELECT status FROM clinics WHERE id=?", (clinic_id,)
        ).fetchone()
        return row and row[0] in ("dead", "lost", "unsubscribed")

    # ── Safe outreach check ───────────────────────────────────────────────────

    def safe_to_call(self, clinic: dict) -> tuple:
        """Return (ok: bool, reason: str)."""
        cid   = clinic["id"]
        score = clinic.get("score", 0)
        if self.is_dead(cid):
            return False, "clinic is dead/unsubscribed"
        if not self.is_contactable(score):
            return False, f"score {score} below threshold {TIER_B}"
        if self.already_called(cid):
            return False, "already called"
        if self.on_cooldown(cid, "call"):
            return False, "call cooldown active"
        return True, "ok"

    def safe_to_email(self, clinic: dict, day: int) -> tuple:
        cid   = clinic["id"]
        score = clinic.get("score", 0)
        if self.is_dead(cid):
            return False, "clinic is dead/unsubscribed"
        if not self.is_contactable(score):
            return False, f"score {score} below threshold"
        if self.already_emailed_day(cid, day):
            return False, f"day-{day} email already sent"
        if self.on_cooldown(cid, "email"):
            return False, "email cooldown active"
        return True, "ok"

    def safe_to_sms(self, clinic: dict) -> tuple:
        cid   = clinic["id"]
        if self.is_dead(cid):
            return False, "clinic is dead/unsubscribed"
        if self.on_cooldown(cid, "sms"):
            return False, "sms cooldown active"
        return True, "ok"

    # ── Pipeline state ────────────────────────────────────────────────────────

    def pipeline_summary(self) -> dict:
        s = {}
        for status in ("new", "contacted", "interested", "booked", "client", "dead", "lost", "nurture"):
            s[status] = self.conn.execute(
                "SELECT COUNT(*) FROM clinics WHERE status=?", (status,)
            ).fetchone()[0]
        s["total"] = self.conn.execute("SELECT COUNT(*) FROM clinics").fetchone()[0]
        s["tier_a_untouched"] = self.conn.execute(
            "SELECT COUNT(*) FROM clinics WHERE score >= ? AND status='new'", (TIER_A,)
        ).fetchone()[0]
        s["warm_leads"] = self.conn.execute(
            "SELECT COUNT(*) FROM replies WHERE classification IN ('interested','curious') AND handled=0"
        ).fetchone()[0]
        return s

    def close(self):
        self.conn.close()


# ── Standalone audit ──────────────────────────────────────────────────────────

def run():
    """Print a pipeline safety audit."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = Coordinator(conn)

    print("=" * 50)
    print("  PIPELINE SAFETY AUDIT")
    print("=" * 50)

    summary = c.pipeline_summary()
    for k, v in summary.items():
        print(f"  {k:<22} {v}")

    print("\n  PER-CLINIC READINESS (score >= 40)")
    rows = conn.execute(
        "SELECT id, name, score, status, phone, email FROM clinics WHERE score >= ? ORDER BY score DESC",
        (TIER_B,),
    ).fetchall()
    for r in rows:
        ok_call, why_call   = c.safe_to_call(dict(r))
        ok_email, why_email = c.safe_to_email(dict(r), 1)
        proof = "✓" if c.has_proof_page(r["id"]) else " "
        call_s  = "✓" if ok_call  else f"✗ {why_call}"
        email_s = "✓" if ok_email else f"✗ {why_email}"
        print(
            f"  [{r['score']:>3}] {r['name'][:36]:<36} "
            f"proof:{proof}  call:{call_s:<20}  email:{email_s}"
        )

    print("=" * 50)
    c.close()


if __name__ == "__main__":
    run()
