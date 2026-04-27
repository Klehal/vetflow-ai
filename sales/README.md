# VetFlow AI — Sales Pipeline

Automated outreach system for acquiring vet clinic clients in Calgary.

## Quick Start

```bash
# Daily operator view
python3 sales/ops.py

# Run full pipeline
python3 sales/run_daily.py

# First client (Tier A only, custom scripts)
python3 sales/agents/first_client_mode.py --call --email

# Place calls to all uncalled clinics
python3 sales/agents/caller.py
```

## Agent Pipeline

| # | Agent | What it does |
|---|-------|-------------|
| 1 | `lead_hunter.py` | Scrape Calgary vet clinics |
| 2 | `lead_scorer.py` | Score 0–100, classify type (chain/emergency/general) |
| 3 | `offer_strategist.py` | Generate 1-sentence hook from verifiable facts |
| 4 | `proof_agent.py` | Build clinic-specific missed-call demo page |
| 5 | `caller.py` | Place Bland.ai voice calls (Tier A first) |
| 6 | `sms_followup.py` | Post-call SMS 30 min later |
| 7 | `sequence_runner.py` | Day 1/3/5/7 email sequence |
| 8 | `reply_handler.py` | Classify inbound replies with GPT |
| 9 | `closer_agent.py` | Send proof page + Calendly to warm leads |
| 10 | `onboarding_agent.py` | Checklist + welcome email on close |
| 11 | `analytics.py` | Daily report + weekly summary |

All agents route through `coordinator.py` — shared cooldown/duplicate-prevention safety layer.

## Tier System

- **Tier A (75+):** Custom GPT script, immediate priority
- **Tier B (40–74):** Standard curiosity script
- **Tier C (<40):** Hold — do not contact
- **Chains (VCA etc.):** –25 pts | **Emergency/24hr:** –10 pts | **Specialists:** –20 pts

## Two-Step CTA

Call/email → "Want me to send you a quick example?" → proof page → Calendly

Never lead with Calendly. Never mention price or "AI receptionist" in outreach.

## See Also

- `OPERATOR_HANDOFF.md` — full operator guide, commands, and playbook
