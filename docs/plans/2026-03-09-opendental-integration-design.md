# OpenDental Integration Design

**Date:** 2026-03-09
**Project:** maoffice — Phase 2
**Status:** Approved

---

## Overview

Replace Phase 1 placeholder data in `maoffice` with live queries against the on-premise OpenDental MySQL database. Add a Slack slash command chatbot for on-demand queries by staff.

---

## Context

- OpenDental runs on a Windows Server on the office LAN.
- The `maoffice` Linux daemon is on the same LAN — MySQL port 3306 is accessible.
- OpenDental ships with MySQL using the default `root` user and empty password.
- Weave (dental communications platform) is out of scope for now; may be integrated in a future phase.

---

## Architecture

```
Windows Server (on-prem)
  └── OpenDental → MySQL (port 3306, LAN-accessible)
        └── user: root / no password (default OD install)

Linux machine (maoffice daemon)
  ├── maoffice/opendental.py      ← NEW: SQL query layer
  ├── maoffice/scheduler.py       ← UPDATED: uses real OD data
  ├── maoffice/slack_bot.py       ← NEW: Slack Bolt socket-mode app
  └── main.py                     ← UPDATED: runs scheduler + Slack bot concurrently
```

**Two new capabilities:**

1. **`opendental.py`** — thin query module with named functions (`get_today_schedule`, `get_daily_production`, `get_aging_report`, `get_open_slots`, `find_patients`). Pure SQL, no ORM, returns plain Python dicts/lists.

2. **`slack_bot.py`** — Slack Bolt app in Socket Mode (outbound WebSocket, no inbound port/firewall change needed). Handles `/od` slash commands. Runs as a thread alongside the existing APScheduler daemon.

---

## New `.env` Variables

```
OD_MYSQL_HOST=<windows-server-ip>
OD_MYSQL_PORT=3306
OD_MYSQL_USER=root
OD_MYSQL_PASSWORD=
OD_MYSQL_DB=opendental
SLACK_APP_TOKEN=<xapp-...>    # Socket Mode app-level token
```

> **Security note:** Using root with empty password is the default OpenDental MySQL setup. A hardening step (creating a read-only `maoffice_reader` user) is recommended before production but not required to ship Phase 2. A `scripts/setup_od_user.sql` will be provided.

---

## Reports & Data

| Report | Delivery | Key OD Tables | Notes |
|---|---|---|---|
| Today's schedule | Morning Slack msg | `appointment`, `patient`, `provider` | Time, provider, confirmed/broken status |
| Cancellations / no-shows | Morning + evening | `appointment` | `AptStatus` IN (Broken, UnschedList) |
| Next 7 days open slots | Morning Slack msg | `appointment`, `schedule` | Unfilled operatory slots by day + provider |
| Daily production | Evening summary | `procedurelog`, `claimproc` | Completed procedures today |
| Collections | Evening summary | `payment`, `claimproc` | Patient + insurance payments received today |
| AR aging | Evening summary (weekly Mon) | `patient`, computed ledger | Outstanding balances: 30/60/90/120+ day buckets |
| Insurance claims | Evening summary | `claim`, `claimproc` | Pending/rejected count + dollar total |
| Patient lookup | On-demand slash cmd | `patient`, `appointment`, `insplan` | Next appt, balance, insurance |

**AI enrichment:** Raw structured data is passed to the existing `ai_summary.py` (local AI at `localhost:4141`) to generate a plain-English evening summary for Dr. Ma — same flow as Phase 1, real numbers.

---

## Slack Slash Commands

Registered as `/od` in the Slack app. Socket Mode — no inbound firewall rule needed.

```
/od schedule          → Today's full appointment list
/od patient <name>    → Patient lookup: next appt, balance, insurance
/od aging             → AR aging report (30/60/90/120+ buckets)
/od production        → Today's production + collections so far
/od openslots         → Open slots this week
/od help              → Lists all commands
```

Responses are sent only to the designated private channel (`C0AJYNM445V`). No patient data goes to DMs or public channels.

---

## Error Handling

- **MySQL unreachable at job time:** Log error; send a Slack warning (`⚠️ Could not reach OpenDental DB — skipping report`) rather than silently failing.
- **MySQL connection:** Short timeout (5s); connections opened per-query, closed immediately (no persistent pool needed for low-frequency jobs).
- **Slash command DB error:** Reply with an error message in Slack so staff know to retry.
- **AI summary failure:** Fall back to raw structured data (existing behavior).

---

## Files Changed / Added

| File | Change |
|---|---|
| `maoffice/opendental.py` | **NEW** — MySQL query functions |
| `maoffice/slack_bot.py` | **NEW** — Slack Bolt socket-mode bot |
| `maoffice/scheduler.py` | **UPDATED** — replace placeholder data with `opendental.*` calls |
| `main.py` | **UPDATED** — start Slack bot thread + scheduler |
| `scripts/setup_od_user.sql` | **NEW** — optional: create read-only MySQL user |
| `.env.example` | **UPDATED** — add OD_MYSQL_* and SLACK_APP_TOKEN vars |
| `requirements.txt` | **UPDATED** — add `PyMySQL`, `slack-bolt` |

---

## Out of Scope (Phase 2)

- Weave integration
- Write/update operations on OpenDental (read-only only)
- Multi-location / multi-provider filtering UI
- OpenDental REST API (direct MySQL is sufficient)
