"""VetFlow Sales — Daily Orchestrator

Run this every morning. Executes all agents in sequence, then fires an
iPhone push notification via ntfy.sh with the day's summary.

Usage:
    python vetflow_sales/run_daily.py

iPhone setup:
    1. Install the free "ntfy" app from the App Store
    2. Subscribe to topic: vetflow-karan-alerts
    (or set NTFY_TOPIC in .env to override)
"""

import os
import sys
import time
import logging
import traceback
import urllib.request
from pathlib import Path
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [run_daily] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_daily")

# ── ntfy.sh config ────────────────────────────────────────────────────────────
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "vetflow-karan-alerts")
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}"


def push_notify(title: str, message: str, priority: str = "default", tags: str = ""):
    """Send a push notification to iPhone via ntfy.sh. Silent on failure."""
    try:
        headers = {
            "Title": title.encode(),
            "Priority": priority.encode(),
            "Content-Type": b"text/plain",
        }
        if tags:
            headers["Tags"] = tags.encode()
        req = urllib.request.Request(
            NTFY_URL,
            data=message.encode(),
            headers={k: v for k, v in headers.items()},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        log.info("Push notification sent: %s", title)
    except Exception as exc:
        log.warning("Push notification failed (non-fatal): %s", exc)


# ── Agent pipeline — CALL-FIRST revenue engine ───────────────────────────────
#
# Tier A (75+): Hunter → Scorer → Personalizer → Offer Strategist → Proof Agent → Caller
# Tier B (40–74): Hunter → Scorer → Personalizer → Offer Strategist → Caller
# All: SMS follow-up → Email → Reply Handler → Closer → Onboarding → Analytics
#
# Each entry: (label, dotted-module, run-function-name)
AGENTS = [
    # ── PHASE 1: Intelligence ─────────────────────────────────────────────
    ("Lead Hunter",       "vetflow_sales.agents.lead_hunter",       "run"),
    ("Lead Scorer",       "vetflow_sales.agents.lead_scorer",       "run"),
    ("Personalizer",      "vetflow_sales.agents.personalizer",      "run"),
    ("Offer Strategist",  "vetflow_sales.agents.offer_strategist",  "run"),
    # ── PHASE 2: Proof (Tier A gets demo page before outreach) ───────────
    ("Proof Agent",       "vetflow_sales.agents.proof_agent",       "run"),
    # ── PHASE 3: Outreach — CALL FIRST ───────────────────────────────────
    ("Caller",            "vetflow_sales.agents.caller",            "main"),
    ("SMS Follow-up",     "vetflow_sales.agents.sms_followup",      "run"),
    ("Sequence Runner",   "vetflow_sales.agents.sequence_runner",   "run"),
    # ── PHASE 4: Conversion ───────────────────────────────────────────────
    ("Reply Handler",     "vetflow_sales.agents.reply_handler",     "run"),
    ("Closer",            "vetflow_sales.agents.closer_agent",      "run"),
    ("Onboarding",        "vetflow_sales.agents.onboarding_agent",  "run"),
    # ── PHASE 5: Reporting ────────────────────────────────────────────────
    ("Analytics",         "vetflow_sales.agents.analytics",         "run"),
]


def _banner(label: str, symbol: str = "─") -> str:
    return f"\n{symbol * 60}\n  {label}\n{symbol * 60}"


def run_agent(label: str, module_path: str, fn_name: str) -> bool:
    """Import module dynamically and call its entry function.
    Returns True on success, False on error.
    Errors are caught so subsequent agents still execute.
    """
    import importlib

    print(_banner(f"STEP: {label}"))
    start = time.perf_counter()

    try:
        mod = importlib.import_module(module_path)
        fn  = getattr(mod, fn_name)
        fn()
        elapsed = time.perf_counter() - start
        log.info(f"[{label}] completed in {elapsed:.1f}s")
        return True

    except ModuleNotFoundError as exc:
        elapsed = time.perf_counter() - start
        log.warning(
            f"[{label}] SKIPPED — module '{module_path}' not found yet: {exc}"
        )
        return False

    except AttributeError as exc:
        elapsed = time.perf_counter() - start
        log.warning(f"[{label}] SKIPPED — no {fn_name}() in '{module_path}': {exc}")
        return False

    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - start
        log.error(f"[{label}] FAILED after {elapsed:.1f}s: {exc}")
        traceback.print_exc()
        return False


def _pipeline_summary() -> str:
    """Pull quick stats from the DB for the push notification body."""
    try:
        import sqlite3
        db_path = ROOT / "data" / "vetflow_sales.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        total    = conn.execute("SELECT COUNT(*) FROM clinics").fetchone()[0]
        contacted = conn.execute(
            "SELECT COUNT(*) FROM clinics WHERE status='contacted'"
        ).fetchone()[0]
        replied  = conn.execute(
            "SELECT COUNT(*) FROM clinics WHERE status='replied'"
        ).fetchone()[0]
        booked   = conn.execute(
            "SELECT COUNT(*) FROM clinics WHERE status='booked'"
        ).fetchone()[0]
        emails_today = conn.execute(
            "SELECT COUNT(*) FROM touchpoints "
            "WHERE channel='email' AND date(sent_at)=date('now')"
        ).fetchone()[0]
        calls_today  = conn.execute(
            "SELECT COUNT(*) FROM touchpoints "
            "WHERE channel='call' AND date(sent_at)=date('now')"
        ).fetchone()[0]
        conn.close()

        return (
            f"Emails today: {emails_today} | Calls today: {calls_today}\n"
            f"Pipeline: {total} clinics | {contacted} contacted | "
            f"{replied} replied | {booked} booked"
        )
    except Exception:
        return "Stats unavailable"


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    wall_start = time.perf_counter()
    run_date   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 60)
    print("  VETFLOW SALES — DAILY ORCHESTRATOR")
    print(f"  {run_date}")
    print("=" * 60)

    # Notify start
    push_notify(
        title="VetFlow 🚀 Daily run starting",
        message=f"Pipeline started at {datetime.now().strftime('%H:%M')}",
        priority="low",
        tags="rocket",
    )

    results = []
    for label, module_path, fn_name in AGENTS:
        ok = run_agent(label, module_path, fn_name)
        results.append((label, ok))

    # ── Final summary ─────────────────────────────────────────────────────
    total_time = time.perf_counter() - wall_start
    passed     = sum(1 for _, ok in results if ok)
    failed     = sum(1 for _, ok in results if not ok)

    print(_banner("DAILY RUN COMPLETE", "="))
    for label, ok in results:
        icon = "✓" if ok else "✗"
        print(f"  [{icon}] {label}")

    print(f"\n  {passed}/{len(results)} agents ran  |  {total_time:.0f}s total")
    print("=" * 60)

    # ── iPhone push notification ───────────────────────────────────────────
    status_line = _pipeline_summary()
    if failed == 0:
        push_notify(
            title=f"VetFlow ✅ Daily run complete ({passed}/{len(results)})",
            message=status_line,
            priority="default",
            tags="white_check_mark",
        )
    else:
        push_notify(
            title=f"VetFlow ⚠️ Run done — {failed} agent(s) failed",
            message=f"{status_line}\nFailed: {', '.join(l for l, ok in results if not ok)}",
            priority="high",
            tags="warning",
        )

    if passed == 0 and len(results) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
