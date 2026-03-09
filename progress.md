# maoffice Progress Log

## 2026-03-09 — Phase 1: Core Slack Integration

### What was built

Standing up the core skeleton to send Slack notifications to the Prime Dental Care workspace.

**Files created:**
- `maoffice/slack_client.py` — Slack SDK wrapper (`send_message`)
- `maoffice/messages.py` — Block Kit message formatters for morning todo + daily summary
- `maoffice/ai_summary.py` — OpenAI-compatible client pointing at local AI server (port 4141)
- `maoffice/scheduler.py` — APScheduler cron jobs (morning + evening) with Phase 1 placeholder data
- `scripts/send_morning.py` — Manual one-shot: send morning todo list now
- `scripts/send_summary.py` — Manual one-shot: send daily summary now
- `main.py` — Daemon entry point (runs scheduler forever)
- `systemd/maoffice.service` — Systemd user service unit
- `.env.example` — Credential template

### Environment

- Venv: `~/pyenvs/maoffice/`
- Slack bot: **@primebot** in workspace **Prime Dental Care**
- Target channel: private channel `C0AJYNM445V`
- Dr Ma's Slack user ID: `UHC2M6UAU` (Joyce Guojun Ma) — @mentioned in every message

### Verified working

- `scripts/send_morning.py` — sends morning todo list with @Dr Ma mention ✅
- `scripts/send_summary.py` — sends daily summary with @Dr Ma mention ✅ (AI falls back to raw text when local server is offline)

### Slack app scopes required

`chat:write`, `chat:write.public`, `groups:read`, `users:read`

---

## Next steps (Phase 2)

- Wire in real OpenDental data instead of placeholder todos/stats
- Connect local AI server (port 4141) for live summarization
- Enable and test systemd service for scheduled delivery
