# OpenDental Integration Progress Log

## 2026-03-09 — Phase 2: OpenDental MySQL Integration + Slack Bot

### Overview

Replaced all Phase 1 placeholder data with live queries against the on-premise OpenDental MySQL
database. Added a Slack `/od` slash command chatbot for on-demand queries by staff.

---

### Architecture

```
Windows Server (on-prem)
  └── OpenDental → MySQL (port 3306, same LAN)
        └── user: root / no password (default OD install)  [10.0.0.166]

Linux machine (maoffice daemon)
  ├── maoffice/opendental.py      ← NEW: SQL query layer
  ├── maoffice/scheduler.py       ← UPDATED: uses real OD data
  ├── maoffice/slack_bot.py       ← NEW: Slack Bolt socket-mode bot
  └── main.py                     ← UPDATED: runs scheduler + Slack bot together
```

**Connection method:** Direct PyMySQL from Linux → Windows Server MySQL (port 3306, LAN).
No middleware. No ORM. All queries use parameterized `%s` placeholders (SQL-injection safe).
Connection timeout: 5 seconds. DictCursor used throughout (rows return as dicts).

---

### Files Created / Modified

| File | Change | Purpose |
|---|---|---|
| `maoffice/opendental.py` | **NEW** | MySQL query layer — all OD data functions |
| `maoffice/slack_bot.py` | **NEW** | Slack Bolt Socket Mode `/od` slash command handler |
| `maoffice/messages.py` | **UPDATED** | Added `build_morning_message_v2()` and `build_summary_message_v2()` |
| `maoffice/scheduler.py` | **REPLACED** | All placeholder data replaced with live `opendental.*` calls |
| `main.py` | **UPDATED** | Starts Slack bot thread + APScheduler daemon |
| `scripts/send_morning.py` | **UPDATED** | Queries live OD data; validates env vars on startup |
| `scripts/send_summary.py` | **UPDATED** | Queries live OD data; validates env vars on startup |
| `scripts/setup_od_user.sql` | **NEW** | Optional: create read-only `maoffice_reader` MySQL user |
| `.env.example` | **UPDATED** | Added `OD_MYSQL_*` and `SLACK_APP_TOKEN` variables |
| `requirements.txt` | **UPDATED** | Added `PyMySQL>=1.1` and `slack-bolt>=1.18` |

---

### OpenDental Query Functions (`maoffice/opendental.py`)

| Function | Tables | Returns |
|---|---|---|
| `get_connection()` | — | PyMySQL connection from env vars; raises `ValueError` if `OD_MYSQL_HOST` unset |
| `get_today_schedule()` | `appointment`, `patient`, `provider` | Today's appointments (status not broken/unscheduled), ordered by time |
| `get_today_cancellations()` | `appointment`, `patient` | Today's broken (`AptStatus=5`) and unscheduled (`AptStatus=2`) appointments |
| `get_open_slots(days_ahead=7)` | `schedule`, `provider`, `appointment` | Working days next N days (SchedType=1) with scheduled hours + appointment count per provider |
| `get_daily_production()` | `procedurelog` | Sum of `ProcFee` for completed procedures today (`ProcStatus=2`); returns `{production, procedure_count}` |
| `get_collections()` | `payment`, `claimproc` | Patient payments (`payment.PayAmt`) + insurance payments (`claimproc.InsPayAmt`) received today |
| `get_aging_report()` | `patient` | Sums pre-computed aging columns (`Bal_0_30`, `Bal_31_60`, `Bal_61_90`, `BalOver90`) — 4 buckets |
| `get_insurance_claims_summary()` | `claim` | Count + total of pending (`ClaimStatus=1`) and rejected (`ClaimStatus=7`) claims from last 90 days |
| `find_patients(search)` | `patient`, `appointment`, `patplan`, `inssub`, `insplan`, `carrier` | Name search (single token or first+last), returns up to 10 matches with next appt + primary carrier |

#### OpenDental AptStatus codes (reference)
```
0 = Scheduled
1 = Complete
2 = UnschedList
3 = ASAP
5 = Broken
```

#### OpenDental schedule.SchedType codes (reference)
```
0 = Office-closed markers (ancient records, not used for scheduling)
1 = Provider working blocks  ← use this to find working days
2 = Blockouts
3 = Employee schedule
```

---

### Actual Schema Notes (discovered from live DB)

These differ from generic OpenDental documentation:

| Topic | Expected (generic docs) | Actual (this instance) |
|---|---|---|
| Aging buckets | `Bal_0_30`, `Bal_31_60`, `Bal_61_90`, `Bal_91_120`, `BalOver120` (5) | `Bal_0_30`, `Bal_31_60`, `Bal_61_90`, `BalOver90` (4) |
| Patient insurance link | `patient.PriPlanNum` | No such column — use `patplan (Ordinal=1) → inssub → insplan → carrier` |
| Open schedule slots | `schedule` rows with `SchedType=0` | `SchedType=0` = office-closed only; working blocks = `SchedType=1` |
| Hygiene appointment provider | appointments linked to hygienist via `ProvNum` | `ProvNum` = primary provider (Dr. Ma); hygienist is in `ProvHyg` — check both when counting per provider |

---

### Scheduled Slack Messages

**Morning message (08:00)** — powered by `build_morning_message_v2()`:
- Today's full appointment list (time, patient, provider, procedure)
- Cancellations / no-shows today
- Working days next 7 days with scheduled hours + appointment count per provider

**Evening summary (18:00)** — powered by `build_summary_message_v2()`:
- Production (total fee + procedure count)
- Collections (patient payments + insurance payments)
- AR aging buckets (0-30 / 31-60 / 61-90 / 90+)
- Insurance claims (pending count + total, rejected count + total)
- Cancellations / no-shows
- AI narrative summary (via local AI server at port 4141)

**AR aging** is included every Monday, or daily when `AGING_DAILY=true` in `.env`.

**DB error handling:** If MySQL is unreachable at job time, a Slack warning is posted
(`⚠️ maoffice: Could not reach OpenDental DB…`) instead of crashing the daemon.

---

### Slack `/od` Slash Commands (`maoffice/slack_bot.py`)

Runs via **Slack Bolt Socket Mode** (outbound WebSocket — no inbound firewall port needed).
Restricted to the designated channel (`SLACK_CHANNEL_ID`); commands from other channels are rejected.

| Command | What it does |
|---|---|
| `/od schedule` | Today's full appointment list + cancellations |
| `/od patient <name>` | Patient lookup — accepts `Tian`, `Ye Tian`, `Tian Ye`, or `Tian, Ye` |
| `/od aging` | AR aging report (0-30 / 31-60 / 61-90 / 90+) |
| `/od production` | Today's production + collections so far |
| `/od openslots` | Working days this week with hours scheduled + appointment count |
| `/od help` | Lists all commands |

---

### Environment Variables

```
OD_MYSQL_HOST=10.0.0.166   # Windows Server running OpenDental
OD_MYSQL_PORT=3306
OD_MYSQL_USER=root
OD_MYSQL_PASSWORD=          # blank — default OD install has no MySQL password
OD_MYSQL_DB=opendental
SLACK_APP_TOKEN=xapp-...    # App-level token for Socket Mode
```

---

### Tests

23 tests across 7 test files, all passing. All tests use `unittest.mock` — no real DB connection needed.

| Test file | Tests | What it covers |
|---|---|---|
| `tests/test_opendental_connection.py` | 2 | `get_connection()` env-var mapping, missing-host error |
| `tests/test_opendental_schedule.py` | 2 | `get_today_schedule()` return type, date filtering |
| `tests/test_opendental_slots.py` | 2 | `get_open_slots()` return type, 2-param date query |
| `tests/test_opendental_production.py` | 2 | `get_daily_production()` and `get_collections()` return shapes |
| `tests/test_opendental_aging.py` | 5 | `get_aging_report()` buckets, `find_patients()` single/two-token/comma search |
| `tests/test_messages_v2.py` | 2 | `build_morning_message_v2()` and `build_summary_message_v2()` formatting |
| `tests/test_slack_bot.py` | 8 | Command parsing + all response formatters |

---

### Service Status

Daemon running as systemd user service (`maoffice.service`).

```bash
systemctl --user status maoffice    # check status
systemctl --user restart maoffice   # restart after .env changes
journalctl --user -u maoffice -n 30 # view recent logs
```

Confirmed log output on startup:
```
Starting Slack Bolt Socket Mode handler…
⚡️ Bolt app is running!
Starting to receive messages from a new connection (session id: …)
Scheduled morning at 08:00 and summary at 18:00 (America/Los_Angeles)
Scheduler started
```

---

### Pending / Next Steps

- **Optional hardening:** Run `scripts/setup_od_user.sql` on the Windows Server to create a read-only `maoffice_reader` MySQL user instead of using `root`
- **Phase 3 ideas:** Weave integration (calls/texts), treatment plan follow-up alerts, recall reminders

---

### Git Commits (Phase 2 + Live Fixes)

```
3d4f292 docs: note ProvHyg pattern in CLAUDE.md
e1fccdc fix: count hygiene appointments for Kate via ProvHyg field
411ca6b docs: update opendental_progress.md with live fixes and schema discoveries
13372d0 docs: add OD schema facts to CLAUDE.md (aging buckets, schedule types)
41d0a6f fix: correct aging buckets and open slots query for this OD instance
9f63ea4 feat: support first+last name search in find_patients
9f85a7d docs: add OpenDental read-only rule and insurance schema to CLAUDE.md
ae757c2 fix: correct find_patients insurance JOIN chain for OpenDental schema
b7cf7e6 docs: add opendental_progress.md for Phase 2 OpenDental integration
81d8eff fix: address code review issues (channel restriction, test mock, import cleanup)
1bb50f6 feat: update scripts to use live OD data; add setup_od_user.sql
4699b5e feat: start Slack bot thread + scheduler in main.py
c8106e8 feat: add Slack Bolt Socket Mode /od slash command handler
d62c6f7 feat: wire scheduler to live OpenDental data (Phase 2)
a653664 feat: add build_morning_message_v2() and build_summary_message_v2() with live data
fc1b16a feat: add get_aging_report(), get_insurance_claims_summary(), find_patients()
d82a540 feat: add get_daily_production() and get_collections()
6fb32b1 feat: add get_open_slots() for next-7-days open schedule
6c9d92a feat: add get_today_schedule() and get_today_cancellations()
c0aadf6 feat: add opendental.get_connection() with env-var config
c34be0a config: add OD_MYSQL_* and SLACK_APP_TOKEN to .env.example
e012f54 Add Phase 2 implementation plan: OpenDental + Slack bot
24ab3ff Add Phase 2 design doc: OpenDental MySQL integration + Slack bot
```


## 2026-03-09 — Phase 2: OpenDental MySQL Integration + Slack Bot

### Overview

Replaced all Phase 1 placeholder data with live queries against the on-premise OpenDental MySQL
database. Added a Slack `/od` slash command chatbot for on-demand queries by staff.

---

### Architecture

```
Windows Server (on-prem)
  └── OpenDental → MySQL (port 3306, same LAN)
        └── user: root / no password (default OD install)

Linux machine (maoffice daemon)
  ├── maoffice/opendental.py      ← NEW: SQL query layer
  ├── maoffice/scheduler.py       ← UPDATED: uses real OD data
  ├── maoffice/slack_bot.py       ← NEW: Slack Bolt socket-mode bot
  └── main.py                     ← UPDATED: runs scheduler + Slack bot together
```

**Connection method:** Direct PyMySQL from Linux → Windows Server MySQL (port 3306, LAN).
No middleware. No ORM. All queries use parameterized `%s` placeholders (SQL-injection safe).
Connection timeout: 5 seconds. DictCursor used throughout (rows return as dicts).

---

### Files Created / Modified

| File | Change | Purpose |
|---|---|---|
| `maoffice/opendental.py` | **NEW** | MySQL query layer — all OD data functions |
| `maoffice/slack_bot.py` | **NEW** | Slack Bolt Socket Mode `/od` slash command handler |
| `maoffice/messages.py` | **UPDATED** | Added `build_morning_message_v2()` and `build_summary_message_v2()` |
| `maoffice/scheduler.py` | **REPLACED** | All placeholder data replaced with live `opendental.*` calls |
| `main.py` | **UPDATED** | Starts Slack bot thread + APScheduler daemon |
| `scripts/send_morning.py` | **UPDATED** | Queries live OD data; validates env vars on startup |
| `scripts/send_summary.py` | **UPDATED** | Queries live OD data; validates env vars on startup |
| `scripts/setup_od_user.sql` | **NEW** | Optional: create read-only `maoffice_reader` MySQL user |
| `.env.example` | **UPDATED** | Added `OD_MYSQL_*` and `SLACK_APP_TOKEN` variables |
| `requirements.txt` | **UPDATED** | Added `PyMySQL>=1.1` and `slack-bolt>=1.18` |

---

### OpenDental Query Functions (`maoffice/opendental.py`)

| Function | Tables | Returns |
|---|---|---|
| `get_connection()` | — | PyMySQL connection from env vars; raises `ValueError` if `OD_MYSQL_HOST` unset |
| `get_today_schedule()` | `appointment`, `patient`, `provider` | Today's appointments (status not broken/unscheduled), ordered by time |
| `get_today_cancellations()` | `appointment`, `patient` | Today's broken (`AptStatus=5`) and unscheduled (`AptStatus=2`) appointments |
| `get_open_slots(days_ahead=7)` | `schedule`, `provider`, `appointment` | Open schedule blocks with no booked appointment, next N days, grouped by date + provider |
| `get_daily_production()` | `procedurelog` | Sum of `ProcFee` for completed procedures today (`ProcStatus=2`); returns `{production, procedure_count}` |
| `get_collections()` | `payment`, `claimproc` | Patient payments (`payment.PayAmt`) + insurance payments (`claimproc.InsPayAmt`) received today |
| `get_aging_report()` | `patient` | Sums pre-computed aging columns (`Bal_0_30`, `Bal_31_60`, `Bal_61_90`, `Bal_91_120`, `BalOver120`) across all active patients with outstanding balances |
| `get_insurance_claims_summary()` | `claim` | Count + total of pending (`ClaimStatus=1`) and rejected (`ClaimStatus=7`) claims from last 90 days |
| `find_patients(search)` | `patient`, `appointment`, `insplan`, `carrier` | Case-insensitive `LName LIKE %search%`, returns up to 10 matches with next appt date + primary carrier |

#### OpenDental AptStatus codes (reference)
```
0 = Scheduled
1 = Complete
2 = UnschedList
3 = ASAP
5 = Broken
```

---

### Scheduled Slack Messages

**Morning message (08:00)** — powered by `build_morning_message_v2()`:
- Today's full appointment list (time, patient, provider, procedure)
- Cancellations / no-shows today
- Open appointment slots for the next 7 days (by date + provider)

**Evening summary (18:00)** — powered by `build_summary_message_v2()`:
- Production (total fee + procedure count)
- Collections (patient payments + insurance payments)
- AR aging buckets (0-30 / 31-60 / 61-90 / 91-120 / 120+)
- Insurance claims (pending count + total, rejected count + total)
- Cancellations / no-shows
- AI narrative summary (via local AI server at port 4141)

**AR aging** is included every Monday, or daily when `AGING_DAILY=true` in `.env`.

**DB error handling:** If MySQL is unreachable at job time, a Slack warning is posted
(`⚠️ maoffice: Could not reach OpenDental DB…`) instead of crashing the daemon.

---

### Slack `/od` Slash Commands (`maoffice/slack_bot.py`)

Runs via **Slack Bolt Socket Mode** (outbound WebSocket — no inbound firewall port needed).
Restricted to the designated channel (`SLACK_CHANNEL_ID`); commands from other channels are rejected.

| Command | What it does |
|---|---|
| `/od schedule` | Today's full appointment list + cancellations |
| `/od patient <name>` | Patient lookup: next appt, balance, insurance |
| `/od aging` | AR aging report (0-30 / 31-60 / 61-90 / 91-120 / 120+) |
| `/od production` | Today's production + collections so far |
| `/od openslots` | Open slots this week |
| `/od help` | Lists all commands |

---

### Environment Variables Added

```
OD_MYSQL_HOST=        # IP address of Windows Server running OpenDental
OD_MYSQL_PORT=3306
OD_MYSQL_USER=root
OD_MYSQL_PASSWORD=    # blank — default OD install has no MySQL password
OD_MYSQL_DB=opendental
SLACK_APP_TOKEN=xapp-...   # App-level token for Socket Mode
```

---

### Tests

21 tests across 6 test files, all passing. All tests use `unittest.mock` — no real DB connection needed.

| Test file | Tests | What it covers |
|---|---|---|
| `tests/test_opendental_connection.py` | 2 | `get_connection()` env-var mapping, missing-host error |
| `tests/test_opendental_schedule.py` | 2 | `get_today_schedule()` return type, date filtering |
| `tests/test_opendental_slots.py` | 2 | `get_open_slots()` return type, 2-param date query |
| `tests/test_opendental_production.py` | 2 | `get_daily_production()` and `get_collections()` return shapes |
| `tests/test_opendental_aging.py` | 3 | `get_aging_report()` buckets, `find_patients()` results + case-insensitivity |
| `tests/test_messages_v2.py` | 2 | `build_morning_message_v2()` and `build_summary_message_v2()` formatting |
| `tests/test_slack_bot.py` | 8 | Command parsing + all response formatters |

---

### Service Status

Daemon running as systemd user service (`maoffice.service`).

```bash
systemctl --user status maoffice    # check status
systemctl --user restart maoffice   # restart after .env changes
journalctl --user -u maoffice -n 30 # view recent logs
```

Confirmed log output on startup:
```
Starting Slack Bolt Socket Mode handler…
⚡️ Bolt app is running!
Starting to receive messages from a new connection (session id: …)
Scheduled morning at 08:00 and summary at 18:00 (America/Los_Angeles)
Scheduler started
```

---

### Pending / Next Steps

- **Add `OD_MYSQL_HOST` to `.env`** — set to the Windows Server IP to enable live data queries
- **Verify `/od` slash command in Slack** — requires the `/od` command to be registered in the Slack app (api.slack.com → Slash Commands)
- **Required new Slack app scopes:** `commands` (in addition to existing scopes)
- **Optional hardening:** Run `scripts/setup_od_user.sql` on the Windows Server to create a read-only `maoffice_reader` MySQL user instead of using `root`
- **Phase 3 ideas:** Weave integration (calls/texts), treatment plan follow-up alerts, recall reminders

---

### Git Commits (Phase 2)

```
81d8eff fix: address code review issues (channel restriction, test mock, import cleanup)
1bb50f6 feat: update scripts to use live OD data; add setup_od_user.sql
4699b5e feat: start Slack bot thread + scheduler in main.py
c8106e8 feat: add Slack Bolt Socket Mode /od slash command handler
d62c6f7 feat: wire scheduler to live OpenDental data (Phase 2)
a653664 feat: add build_morning_message_v2() and build_summary_message_v2() with live data
fc1b16a feat: add get_aging_report(), get_insurance_claims_summary(), find_patients()
d82a540 feat: add get_daily_production() and get_collections()
6fb32b1 feat: add get_open_slots() for next-7-days open schedule
6c9d92a feat: add get_today_schedule() and get_today_cancellations()
c0aadf6 feat: add opendental.get_connection() with env-var config
c34be0a config: add OD_MYSQL_* and SLACK_APP_TOKEN to .env.example
e012f54 Add Phase 2 implementation plan: OpenDental + Slack bot
24ab3ff Add Phase 2 design doc: OpenDental MySQL integration + Slack bot
```
