#!/usr/bin/env python3
"""VetFlow AI — Operator Command Centre

Single command to see everything that matters right now.

Usage:
    python vetflow_sales/ops.py              # daily health view
    python vetflow_sales/ops.py --full       # full pipeline detail
    python vetflow_sales/ops.py --hot        # hot leads only
    python vetflow_sales/ops.py --weekly     # weekly summary
    python vetflow_sales/ops.py --audit      # coordinator safety audit
    python vetflow_sales/ops.py --tier-a     # Tier A status only
"""

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]   # Business project/
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "data" / "vetflow_sales.db"
HOT_LEADS_FILE = PROJECT_ROOT / "vetflow_sales" / "hot_leads.txt"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def scalar(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return (r[0] or 0) if r else 0


# ── Sections ──────────────────────────────────────────────────────────────────

def section_pipeline(conn):
    lines = ["PIPELINE"]
    total = scalar(conn, "SELECT COUNT(*) FROM clinics")
    for s in ("new", "contacted", "interested", "booked", "client", "dead", "nurture"):
        n = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status=?", (s,))
        marker = " ← MONEY" if s == "interested" else (" ← CLOSE" if s == "booked" else "")
        if n or s in ("interested", "booked", "client"):
            lines.append(f"  {s:<15} {n}{marker}")

    tier_a = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE score>=75")
    tier_b = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE score>=40 AND score<75")
    tier_a_fresh = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE score>=75 AND status='new'")
    lines.append(f"  {'Tier A (75+)':<15} {tier_a}  ({tier_a_fresh} untouched)")
    lines.append(f"  {'Tier B (40-74)':<15} {tier_b}")
    lines.append(f"  {'TOTAL':<15} {total}")
    return lines


def section_today(conn):
    today = date.today().isoformat()
    lines = ["TODAY'S OUTREACH"]
    for ch in ("call", "sms", "email"):
        n = scalar(
            conn,
            "SELECT COUNT(*) FROM touchpoints WHERE channel=? AND date(sent_at)=? AND status NOT IN ('error','failed','queued')",
            (ch, today),
        )
        lines.append(f"  {ch:<8} {n}")
    queued = scalar(conn, "SELECT COUNT(*) FROM touchpoints WHERE status='queued'")
    if queued:
        lines.append(f"  {'queued':<8} {queued}  (SMS pending)")
    return lines


def section_all_time(conn):
    lines = ["ALL TIME"]
    calls  = scalar(conn, "SELECT COUNT(*) FROM touchpoints WHERE channel='call' AND status NOT IN ('error','failed')")
    emails = scalar(conn, "SELECT COUNT(*) FROM touchpoints WHERE channel='email' AND status='sent'")
    sms    = scalar(conn, "SELECT COUNT(*) FROM touchpoints WHERE channel='sms' AND status='sent'")
    replies = scalar(conn, "SELECT COUNT(*) FROM replies")
    interested = scalar(conn, "SELECT COUNT(*) FROM replies WHERE classification='interested'")
    curious    = scalar(conn, "SELECT COUNT(*) FROM replies WHERE classification='curious'")
    lines.append(f"  Calls placed:    {calls}")
    lines.append(f"  Emails sent:     {emails}")
    lines.append(f"  SMS sent:        {sms}")
    lines.append(f"  Replies:         {replies}")
    lines.append(f"  Interested:      {interested}")
    lines.append(f"  Curious:         {curious}")
    return lines


def section_proof(conn):
    lines = ["PROOF PAGES"]
    live  = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE proof_page_url LIKE 'http%'")
    miss  = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE score>=40 AND (proof_page_url IS NULL OR proof_page_url='')")
    qa_ok = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE proof_qa_score>=70")
    qa_weak = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE proof_page_url LIKE 'http%' AND (proof_qa_score<70 OR proof_qa_score IS NULL)")
    lines.append(f"  Ready (URL set): {live}")
    lines.append(f"  Missing:         {miss}")
    lines.append(f"  QA score 70+:    {qa_ok}")
    if qa_weak:
        lines.append(f"  ⚠ QA weak:      {qa_weak}  (run proof_agent for details)")
    return lines


def section_tier_a(conn):
    lines = ["TIER A STATUS (score 75+)"]
    rows = conn.execute(
        """SELECT name, score, status, phone, email,
                  proof_page_url, offer_hook, clinic_type,
                  (SELECT COUNT(*) FROM touchpoints t WHERE t.clinic_id=clinics.id) as touches,
                  (SELECT MAX(sent_at) FROM touchpoints t WHERE t.clinic_id=clinics.id) as last_touch
           FROM clinics WHERE score>=75 ORDER BY score DESC"""
    ).fetchall()
    for r in rows:
        proof  = "✓" if (r["proof_page_url"] or "").startswith("http") else "✗"
        hook   = "✓" if r["offer_hook"] else "✗"
        called = "✓" if r["touches"] else "○"
        email  = "E" if r["email"] else " "
        phone  = "P" if r["phone"] else " "
        ctype  = r["clinic_type"] or "general"
        lines.append(
            f"  [{r['score']:>3}] {r['name'][:38]:<38} {r['status']:<12} "
            f"proof:{proof} hook:{hook} called:{called} {email}{phone} [{ctype}]"
        )
    return lines


def section_hot_leads(conn):
    lines = ["HOT LEADS (unhandled warm replies)"]
    rows = conn.execute(
        """SELECT r.classification, c.name, c.email, r.body, r.received_at
           FROM replies r
           JOIN clinics c ON c.id=r.clinic_id
           WHERE r.handled=0 AND r.classification IN ('interested','curious','objection')
           ORDER BY r.received_at DESC"""
    ).fetchall()
    if not rows:
        lines.append("  None — keep outreach going")
        return lines
    for r in rows:
        when = r["received_at"][:10] if r["received_at"] else "?"
        lines.append(f"  [{r['classification'].upper():<12}] {r['name'][:35]:<35} {when}")
        lines.append(f"    → {(r['body'] or '')[:80].strip()}")
    return lines


def section_bottleneck(conn):
    calls  = scalar(conn, "SELECT COUNT(*) FROM touchpoints WHERE channel='call' AND status NOT IN ('error','failed')")
    replies = scalar(conn, "SELECT COUNT(*) FROM replies")
    interested = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status='interested'")
    booked = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status='booked'")
    tier_a_fresh = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE score>=75 AND status='new'")
    proof_live = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE proof_page_url LIKE 'http%'")

    lines = ["BOTTLENECK & NEXT MOVE"]

    if calls == 0:
        lines.append("  ⚠ NO CALLS PLACED YET — this is the #1 blocker")
        lines.append("    Run: python vetflow_sales/agents/first_client_mode.py --call --email")
        lines.append("         python vetflow_sales/agents/caller.py")
    elif replies == 0:
        lines.append("  Calls placed but 0 replies — normal at this stage")
        lines.append("  • Follow up with Day-3 SMS + email on contacted clinics")
        lines.append("  • Run first_client_mode.py --call for remaining Tier A")
    elif interested == 0 and replies > 0:
        lines.append("  Replies coming in but none classified interested yet")
        lines.append("  • Review reply_handler classifications")
        lines.append("  • Run: python vetflow_sales/agents/closer_agent.py")
    elif booked == 0 and interested > 0:
        lines.append(f"  {interested} interested lead(s) — close them NOW")
        lines.append("  • Check hot_leads.txt for context")
        lines.append("  • Run: python vetflow_sales/agents/closer_agent.py")
    else:
        lines.append("  System running — keep pipeline full")

    if tier_a_fresh > 0:
        lines.append(f"  • {tier_a_fresh} Tier A clinic(s) still untouched — call them first")

    if proof_live == 0:
        lines.append("  ⚠ Proof pages not yet public. Enable GitHub Pages:")
        lines.append("    github.com/Klehal/vetflow-ai → Settings → Pages → Source: main /docs")

    return lines


def section_onboarding(conn):
    rows = conn.execute(
        "SELECT name, status FROM clinics WHERE status IN ('booked','client') ORDER BY updated_at DESC"
    ).fetchall()
    if not rows:
        return []
    lines = ["ONBOARDING QUEUE"]
    for r in rows:
        lines.append(f"  [{r['status'].upper()}] {r['name']}")
    return lines


def section_revenue(conn):
    closed  = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status='client'")
    mrr     = closed * 497.0
    booked  = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status='booked'")
    interested = scalar(conn, "SELECT COUNT(*) FROM clinics WHERE status='interested'")
    pipeline_value = interested * 1997 * 0.20
    lines = ["REVENUE"]
    lines.append(f"  Clients:         {closed}")
    lines.append(f"  MRR:            ${mrr:,.0f}/mo")
    lines.append(f"  Demos booked:    {booked}")
    lines.append(f"  Pipeline value: ${pipeline_value:,.0f}  (20% close on {interested} interested)")
    return lines


def section_weekly(conn):
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    lines = ["LAST 7 DAYS"]
    for ch in ("call", "sms", "email"):
        n = scalar(conn,
            "SELECT COUNT(*) FROM touchpoints WHERE channel=? AND date(sent_at)>=? AND status NOT IN ('error','failed','queued')",
            (ch, week_ago))
        lines.append(f"  {ch:<8} {n}")
    r7 = scalar(conn,
        "SELECT COUNT(*) FROM replies WHERE date(received_at)>=?", (week_ago,))
    lines.append(f"  replies  {r7}")
    return lines


# ── Full coordinator audit ────────────────────────────────────────────────────

def run_audit(conn):
    from vetflow_sales.agents.coordinator import Coordinator, TIER_B
    c = Coordinator(conn)
    rows = conn.execute(
        "SELECT id, name, score, status, phone, email, clinic_type FROM clinics WHERE score>=? ORDER BY score DESC",
        (TIER_B,),
    ).fetchall()
    print("\n" + "=" * 60)
    print("  COORDINATOR SAFETY AUDIT")
    print("=" * 60)
    for r in rows:
        ok_call,  r_call  = c.safe_to_call(dict(r))
        ok_email, r_email = c.safe_to_email(dict(r), 1)
        proof = "✓" if c.has_proof_page(r["id"]) else "✗"
        cs = "✓" if ok_call  else f"✗({r_call[:20]})"
        es = "✓" if ok_email else f"✗({r_email[:20]})"
        print(f"  [{r['score']:>3}] {r['name'][:36]:<36} "
              f"proof:{proof}  call:{cs:<24}  email:{es}")
    print("=" * 60)


# ── Main ──────────────────────────────────────────────────────────────────────

def print_dashboard(args):
    conn = get_db()
    today_str = datetime.now().strftime("%A, %B %d %Y  %H:%M")

    print("\n" + "=" * 60)
    print("  VETFLOW AI — OPERATOR DASHBOARD")
    print(f"  {today_str}")
    print("=" * 60)

    sections = [
        section_pipeline(conn),
        section_today(conn),
        section_proof(conn),
        section_tier_a(conn),
        section_hot_leads(conn),
        section_bottleneck(conn),
        section_revenue(conn),
    ]

    if args.full or args.weekly:
        sections.insert(3, section_all_time(conn))
        sections.insert(4, section_weekly(conn))

    if args.full:
        ob = section_onboarding(conn)
        if ob:
            sections.append(ob)

    for section in sections:
        print()
        for line in section:
            print(line)

    if args.hot:
        print()
        for line in section_hot_leads(conn):
            print(line)

    if args.audit:
        run_audit(conn)

    if args.tier_a:
        print()
        for line in section_tier_a(conn):
            print(line)

    print("\n" + "=" * 60)
    print("  COMMANDS")
    print("  Run pipeline:    python vetflow_sales/run_daily.py")
    print("  First client:    python vetflow_sales/agents/first_client_mode.py --call --email")
    print("  Place calls:     python vetflow_sales/agents/caller.py")
    print("  Closer:          python vetflow_sales/agents/closer_agent.py")
    print("  Safety audit:    python vetflow_sales/ops.py --audit")
    print("=" * 60 + "\n")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VetFlow Ops Dashboard")
    parser.add_argument("--full",    action="store_true", help="Show all sections")
    parser.add_argument("--hot",     action="store_true", help="Hot leads only")
    parser.add_argument("--weekly",  action="store_true", help="Include weekly summary")
    parser.add_argument("--audit",   action="store_true", help="Run coordinator safety audit")
    parser.add_argument("--tier-a",  dest="tier_a", action="store_true", help="Tier A status")
    args = parser.parse_args()
    print_dashboard(args)
