#!/usr/bin/env python3
"""Proof Agent — generates a clinic-specific "missed call recovery demo" web page.

For each Tier A clinic (score 75+), builds a clean, one-screen HTML page that:
  - Shows the clinic's name and context
  - Visualises the 4-step missed-call recovery flow
  - Feels personal, not generic
  - Ends with a soft Calendly CTA

Pages are uploaded to Railway at /demo/{slug} and the URL is stored in
clinics.proof_page_url for use by the Closer Agent and call scripts.

The "proof" replaces fake case studies. It's real because it shows exactly
what WOULD happen for their specific clinic — no fabricated numbers.
"""

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vetflow.proof_agent")

DB_PATH     = PROJECT_ROOT / "data" / "vetflow_sales.db"
OUTPUT_DIR  = PROJECT_ROOT / "vetflow_sales" / "proof_pages"
RAILWAY_URL = "https://vetflow-ai-production.up.railway.app"
CALENDLY    = "https://calendly.com/vetflow-ai/15-min-discovery-call"
MIN_SCORE   = 40   # generate proof pages for all scored clinics, Tier A first


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def make_slug(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")[:50]
    return slug


def clinics_needing_proof(conn) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT id, name, phone, email, google_rating, review_count,
                  has_online_booking, after_hours_gap, score,
                  offer_hook, ai_insight
           FROM clinics
           WHERE score >= ?
             AND (proof_page_url IS NULL OR proof_page_url = '')
           ORDER BY score DESC""",
        (MIN_SCORE,),
    ).fetchall()]


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{clinic_name} — Missed Call Recovery Demo</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#f8fafc;color:#1e293b;line-height:1.6}}
    .wrap{{max-width:580px;margin:0 auto;padding:32px 20px 60px}}
    .badge{{display:inline-block;background:#dbeafe;color:#1e40af;
            font-size:12px;font-weight:600;padding:4px 10px;
            border-radius:20px;letter-spacing:.5px;margin-bottom:20px}}
    h1{{font-size:22px;font-weight:700;line-height:1.3;margin-bottom:8px}}
    .sub{{color:#64748b;font-size:15px;margin-bottom:28px}}
    .hook{{background:#fff;border-left:3px solid #6366f1;
           padding:14px 16px;border-radius:0 8px 8px 0;
           font-size:14px;color:#475569;margin-bottom:28px}}
    .flow{{background:#fff;border-radius:12px;padding:24px;
           box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:28px}}
    .flow h2{{font-size:14px;font-weight:600;color:#64748b;
              text-transform:uppercase;letter-spacing:.5px;margin-bottom:18px}}
    .step{{display:flex;align-items:flex-start;margin-bottom:18px}}
    .step:last-child{{margin-bottom:0}}
    .num{{width:28px;height:28px;border-radius:50%;background:#6366f1;
          color:#fff;font-size:13px;font-weight:700;display:flex;
          align-items:center;justify-content:center;flex-shrink:0;margin-right:12px;margin-top:1px}}
    .step-body strong{{display:block;font-size:14px;font-weight:600;color:#1e293b}}
    .step-body span{{font-size:13px;color:#64748b}}
    .divider{{border:none;border-top:1px solid #e2e8f0;margin:24px 0}}
    .cta-block{{text-align:center}}
    .cta-block p{{font-size:14px;color:#64748b;margin-bottom:16px}}
    .cta{{display:inline-block;background:#6366f1;color:#fff;
          padding:13px 28px;border-radius:8px;font-size:15px;
          font-weight:600;text-decoration:none;transition:background .2s}}
    .cta:hover{{background:#4f46e5}}
    .footer{{margin-top:40px;text-align:center;font-size:12px;color:#94a3b8}}
  </style>
</head>
<body>
<div class="wrap">
  <div class="badge">VetFlow AI · Calgary, AB</div>
  <h1>Here's how missed call recovery would work at {clinic_name}</h1>
  <p class="sub">A quick look at exactly what happens when a call comes in and doesn't get picked up.</p>

  {hook_block}

  <div class="flow">
    <h2>The 4-step flow — runs automatically, 24/7</h2>

    <div class="step">
      <div class="num">1</div>
      <div class="step-body">
        <strong>Call comes in — no one picks up</strong>
        <span>Could be lunch hour, after closing, or when staff are with a patient.</span>
      </div>
    </div>

    <div class="step">
      <div class="num">2</div>
      <div class="step-body">
        <strong>Automatic text sent within 60 seconds</strong>
        <span>"Hi, this is {clinic_name} — sorry we missed your call! Are you looking to book an appointment? Reply here and we'll get you taken care of."</span>
      </div>
    </div>

    <div class="step">
      <div class="num">3</div>
      <div class="step-body">
        <strong>Client responds — booking captured</strong>
        <span>The system handles the back-and-forth, books the slot, and sends a confirmation. No staff needed.</span>
      </div>
    </div>

    <div class="step">
      <div class="num">4</div>
      <div class="step-body">
        <strong>You see it in your dashboard</strong>
        <span>New appointment logged. A booking that would have gone to voicemail — and likely a competitor — is now yours.</span>
      </div>
    </div>
  </div>

  <p style="font-size:14px;color:#475569;margin-bottom:28px">
    This runs for {clinic_name} every time a call is missed — nights, weekends,
    busy periods. No extra staff. No extra software for your team to learn.
  </p>

  <hr class="divider">

  <div class="cta-block">
    <p>Does this look useful? Takes 15 minutes to see if it's a fit for your clinic.</p>
    <a href="{calendly}" class="cta">Book a quick call with Karan →</a>
  </div>

  <div class="footer">
    Built by Karan &middot; VetFlow AI &middot; Calgary, AB &middot; vetflow.ai@gmail.com
  </div>
</div>
</body>
</html>
"""


def build_html(clinic: dict) -> str:
    name  = clinic["name"]
    hook  = clinic.get("offer_hook") or clinic.get("ai_insight") or ""

    if hook:
        hook_block = f'<div class="hook">{hook}</div>'
    else:
        hook_block = ""

    return HTML_TEMPLATE.format(
        clinic_name=name,
        hook_block=hook_block,
        calendly=CALENDLY,
    )


def upload_to_railway(slug: str, clinic_name: str, html: str) -> str:
    """POST the demo page to Railway and return the public URL."""
    payload = json.dumps({
        "slug":        slug,
        "clinic_name": clinic_name,
        "html":        html,
    })
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST", f"{RAILWAY_URL}/api/admin/demo",
        "-H", "Content-Type: application/json",
        "-d", payload,
        "--max-time", "20",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    *body_lines, code = proc.stdout.strip().split("\n")
    body = "\n".join(body_lines)
    if int(code) in (200, 201):
        return f"{RAILWAY_URL}/demo/{slug}"
    # Railway may be down — fall back to a local file URL note
    logger.warning("Railway upload returned HTTP %s — page saved locally only", code)
    return f"[local] vetflow_sales/proof_pages/{slug}.html"


def qa_check(clinic: dict, html: str) -> int:
    """
    Score proof page quality 0-100.  Stored in clinics.proof_qa_score.

    Points awarded:
      +35  Clinic name appears in HTML (specificity check)
      +25  Real review count (>0) mentioned in page or hook
      +20  Real rating mentioned in page or hook
      +20  offer_hook is filled (non-empty, non-generic)
    """
    score = 0
    name  = clinic.get("name", "").strip()
    hook  = clinic.get("offer_hook") or ""
    reviews = clinic.get("review_count") or 0
    rating  = clinic.get("google_rating")

    if name and name.lower() in html.lower():
        score += 35

    if reviews and reviews > 0 and (
        str(reviews) in html or str(reviews) in hook
    ):
        score += 25

    if rating and (
        str(rating) in html or str(rating) in hook
    ):
        score += 20

    if hook and len(hook.strip()) > 20:
        score += 20

    return min(score, 100)


def rescore_qa_all():
    """Rescore proof_qa_score for all clinics that have a proof page URL set.
    Reads the locally saved HTML if available; falls back to scoring from clinic data only.
    Run this once after upgrading from a version that didn't have QA scoring.
    """
    conn = get_db()
    try:
        conn.execute("ALTER TABLE clinics ADD COLUMN proof_qa_score INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass

    rows = conn.execute(
        """SELECT id, name, google_rating, review_count, offer_hook, ai_insight, proof_page_url
           FROM clinics WHERE proof_page_url LIKE 'http%' OR proof_page_url LIKE '[local]%'"""
    ).fetchall()

    updated = 0
    for r in rows:
        clinic = dict(r)
        slug   = make_slug(clinic["name"])
        local  = OUTPUT_DIR / f"{slug}.html"
        if local.exists():
            html = local.read_text(encoding="utf-8")
        else:
            # No local file — build a dummy HTML from the hook to approximate
            html = f"<html><body>{clinic.get('offer_hook','')}{clinic['name']}</body></html>"

        qa = qa_check(clinic, html)
        conn.execute("UPDATE clinics SET proof_qa_score=? WHERE id=?", (qa, clinic["id"]))
        logger.info("  QA %3d/100  %s", qa, clinic["name"])
        updated += 1

    conn.commit()
    conn.close()
    logger.info("QA rescore complete — %d clinics updated.", updated)
    return updated


def run():
    logger.info("Proof Agent starting...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    clinics = clinics_needing_proof(conn)
    logger.info("Clinics needing proof page: %d", len(clinics))

    # Ensure proof_qa_score column exists
    try:
        conn.execute("ALTER TABLE clinics ADD COLUMN proof_qa_score INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass

    generated = 0
    for clinic in clinics:
        name = clinic["name"]
        slug = make_slug(name)
        html = build_html(clinic)

        # QA score before saving
        qa = qa_check(clinic, html)

        # Save locally
        local_path = OUTPUT_DIR / f"{slug}.html"
        local_path.write_text(html, encoding="utf-8")
        logger.info("  %-42s → saved locally  QA=%d/100", name, qa)

        # Upload to Railway
        url = upload_to_railway(slug, name, html)

        # Store URL + QA score in DB
        conn.execute(
            "UPDATE clinics SET proof_page_url=?, proof_qa_score=?, updated_at=? WHERE id=?",
            (url, qa, datetime.now().isoformat(), clinic["id"]),
        )
        conn.commit()

        if url.startswith("http"):
            logger.info("       URL: %s", url)
        else:
            logger.info("       URL: (local only — Railway unreachable)")

        if qa < 70:
            logger.warning("  ⚠ QA score %d <70 for %s — hook or clinic data missing", qa, name)

        generated += 1

    conn.close()
    logger.info("Proof Agent done. Generated %d pages.", generated)


if __name__ == "__main__":
    run()
