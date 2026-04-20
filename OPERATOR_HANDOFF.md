# VetFlow AI — Operator Handoff
**Last updated:** 2026-04-19  
**Status:** System fully built, 0 calls placed, 10 emails sent, 28 Calgary clinics in DB

---

## Current State at a Glance

| Item | Status |
|------|--------|
| Calgary clinics in DB | 28 |
| Tier A (score 75+) | 3 — Fish Creek, Petropolitan, Canine Companion |
| Emails sent | 10 (Day-1 sequence) |
| Calls placed | 0 ← **Start here** |
| Proof pages live | 23 (GitHub Pages, pending manual Pages enable) |
| QA score 70+ | 23/23 |
| Hot leads | 0 |
| MRR | $0 |

---

## Fastest Path to First 3 Clients

### Step 1 — Enable GitHub Pages (5 min, one-time)
Go to: `github.com/Klehal/vetflow-ai` → Settings → Pages → Source: **main**, folder: **/docs**  
This makes every proof page live at `https://klehal.github.io/vetflow-ai/demo/{slug}.html`

Without this, the proof page links in emails/calls 404.

### Step 2 — Call Fish Creek Pet Hospital RIGHT NOW
```bash
python3 vetflow_sales/agents/first_client_mode.py --call --email
```
This targets only the 3 Tier A clinics with GPT-generated custom scripts.  
Fish Creek is the only one not yet contacted.

### Step 3 — Call all 27 remaining clinics
```bash
python3 vetflow_sales/agents/caller.py
```
Calls up to 10 clinics per run. Run it again until all 27 are called.  
After each call, a follow-up SMS is queued automatically.

### Step 4 — Send follow-up SMS (30+ min after calls)
```bash
python3 vetflow_sales/agents/sms_followup.py
```
Sends the post-call SMS: "Just tried calling — when you miss a call, do you text them back or does it go to voicemail?"

### Step 5 — Monitor daily
```bash
python3 vetflow_sales/ops.py
```
Tells you exactly what to do next.

### Step 6 — When a reply comes in
Reply handler runs automatically in the daily pipeline.  
For hot leads, check `vetflow_sales/hot_leads.txt`  
Then run the closer:
```bash
python3 vetflow_sales/agents/closer_agent.py
```

---

## Full Command Reference

| Command | What it does |
|---------|-------------|
| `python3 vetflow_sales/ops.py` | Full operator dashboard |
| `python3 vetflow_sales/ops.py --hot` | Hot leads only |
| `python3 vetflow_sales/ops.py --audit` | Coordinator safety audit per clinic |
| `python3 vetflow_sales/ops.py --tier-a` | Tier A clinic detail |
| `python3 vetflow_sales/run_daily.py` | Full 12-agent pipeline (use for daily automation) |
| `python3 vetflow_sales/agents/first_client_mode.py --call --email` | Tier A custom outreach |
| `python3 vetflow_sales/agents/caller.py` | Place Bland.ai calls to all uncalled clinics |
| `python3 vetflow_sales/agents/sms_followup.py` | Send queued post-call SMS |
| `python3 vetflow_sales/agents/closer_agent.py` | Handle unactioned hot leads |
| `python3 vetflow_sales/agents/proof_agent.py` | Regenerate/upload proof pages |
| `python3 vetflow_sales/agents/analytics.py` | Generate daily report |
| `python3 vetflow_sales/agents/coordinator.py` | Standalone safety audit |

---

## Agent Pipeline (run_daily.py order)

```
1. Lead Hunter       — scrape new Calgary vet clinics
2. Lead Scorer       — score 0-100, classify clinic type
3. Personalizer      — extract insight / revenue estimate
4. Offer Strategist  — generate 1-sentence hook from facts
5. Proof Agent       — build clinic-specific demo page
6. Caller            — place Bland.ai calls (Tier A first)
7. SMS Follow-up     — send post-call SMS (30 min later)
8. Sequence Runner   — send Day-1/3/5/7 emails
9. Reply Handler     — classify inbound replies with GPT
10. Closer           — send proof page + Calendly to warm leads
11. Onboarding       — trigger checklist for booked/client
12. Analytics        — daily report + save to reports/
```

---

## Tier System

| Tier | Score | Action |
|------|-------|--------|
| A | 75+ | Custom GPT script + immediate outreach (3 clinics) |
| B | 40–74 | Standard script (14 clinics) |
| C | <40 | Hold — do not contact |

**Chain penalty:** VCA Canada → -25 pts  
**Specialist penalty:** -20 pts  
**Emergency/24hr penalty:** -10 pts

---

## Cooldown Windows (enforced by Coordinator)

| Channel | Cooldown |
|---------|----------|
| Call | 3 days |
| SMS | 2 days |
| Email | 2 days |

The Coordinator also prevents: dead clinic contact, duplicate touchpoints, below-threshold outreach.

---

## Two-Step CTA (never jump straight to Calendly)

1. **Call/SMS/Email Day 1:** "Want me to send you a quick example?"
2. **If yes → Closer sends proof page:** `https://klehal.github.io/vetflow-ai/demo/{slug}.html`
3. **Proof page → Calendly:** "Book a quick call with Karan →"

**Never mention price or "AI receptionist" in outreach.**  
**Use "missed call recovery system" or just describe what it does.**

---

## Reply Classifications

| Classification | Status update | Action |
|----------------|--------------|--------|
| interested | → interested | Closer sends proof page immediately |
| curious | → contacted | Closer asks a follow-up question |
| objection | no change | Closer reframes + offers 15 min |
| already_have_process | → nurture | Gracious exit, door open |
| not_now | → nurture | No action, revisit in 3 months |
| wrong_person | → contacted | Ask for right contact |
| unsubscribe | → dead | Never contact again |
| out_of_office | no change | Wait for real reply |

---

## Proof Pages

All 23 proof pages are saved locally at `vetflow_sales/proof_pages/`  
They're also committed to `vetflow-ai/docs/demo/` (GitHub repo)  
URLs stored as `https://klehal.github.io/vetflow-ai/demo/{slug}.html`

**Enable GitHub Pages once:** Settings → Pages → main /docs  
After that, all 23 pages are live instantly.

---

## iPhone Notifications

Notifications fire at:
- **Pipeline start** — low priority (blue)
- **Pipeline complete** — default priority with stats (green)
- **Failures detected** — high priority (orange)

To receive them:
1. Install **ntfy** app (free, iOS App Store)
2. Subscribe to topic: `vetflow-karan-alerts`

---

## Expansion Conditions (when to hire / add channels)

| Trigger | Action |
|---------|--------|
| 3+ interested leads in pipeline | Spend 2hrs/day on manual follow-up instead of running closer automatically |
| 1st client signed | Immediately run `first_client_mode.py` on remaining untouched Tier A |
| 5 clients | Add Lead Hunter for Edmonton/Airdrie |
| 10 clients ($4,970 MRR) | Hire part-time VA for manual outreach on Tier B |
| 20 clients ($9,940 MRR) | Automate with full SMS/email sequences, stop manual calls |

---

## File Structure (key files)

```
Business project/
├── data/vetflow_sales.db          # All clinic data, touchpoints, replies
├── vetflow_sales/
│   ├── ops.py                     # Operator dashboard (run this daily)
│   ├── run_daily.py               # Full pipeline orchestrator
│   ├── hot_leads.txt              # Warm replies log (check this)
│   ├── agents/
│   │   ├── coordinator.py         # Safety layer (imported by all agents)
│   │   ├── lead_hunter.py         # Scrape clinics
│   │   ├── lead_scorer.py         # Score + classify clinics
│   │   ├── personalizer.py        # Clinic insight extraction
│   │   ├── offer_strategist.py    # Hook generation
│   │   ├── proof_agent.py         # Demo page builder + QA
│   │   ├── caller.py              # Bland.ai voice calls
│   │   ├── sms_followup.py        # Post-call SMS
│   │   ├── sequence_runner.py     # Email sequences
│   │   ├── reply_handler.py       # GPT reply classifier
│   │   ├── closer_agent.py        # Warm lead handler
│   │   ├── onboarding_agent.py    # Post-close checklist
│   │   ├── analytics.py           # Daily report
│   │   └── first_client_mode.py   # Tier A custom outreach
│   ├── proof_pages/               # Local HTML files
│   ├── reports/                   # Daily report archives
│   ├── onboarding/                # Per-client onboarding checklists
│   └── templates/                 # Email/SMS templates
└── OPERATOR_HANDOFF.md            # This file
```

---

## What to Do When...

**"No replies after 5 days"**  
→ All 10 emails sent. Check spam — follow up manually with personal email to top 3.  
→ Run caller.py — calls get 3-5x reply rate vs email cold outreach.

**"Got a reply but it went to voicemail"**  
→ That's normal. SMS follow-up fires automatically.  
→ Check hot_leads.txt for classified replies.

**"Bland.ai call failed with 402"**  
→ Top up Bland.ai balance at app.bland.ai (add $20 for ~140+ calls).

**"Bland.ai call failed with 400"**  
→ Check Canadian number format — must be +1XXXXXXXXXX.  
→ Check payload: no transfer_phone_number on new accounts.

**"Proof page links 404"**  
→ GitHub Pages not enabled. Go to Klehal/vetflow-ai → Settings → Pages → main /docs.

**"SendGrid email bounced"**  
→ Clinic email is bad. Mark manually in DB:  
  `UPDATE clinics SET email=NULL WHERE name='...';`

**"Clinic says they already have a system"**  
→ Reply handler classifies as `already_have_process` → status = nurture  
→ Closer sends gracious exit email.  
→ Re-activate in 6 months (change status back to 'new').

---

## Revenue Model

- Price: **$497–$697/mo** (sell at $497, raise on renewal)
- Setup fee: **$0** (waive for first 3 clients, builds trust)
- Pipeline value formula: `interested_count × $1,997 × 20%`
- Break-even: **6 clients** covers all tool costs ($2,982/mo)
- Goal: **10 clients = $4,970 MRR**

---

*System built by Claude. Questions → read ops.py comments or re-run Claude with this file as context.*
