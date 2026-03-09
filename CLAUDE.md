# maoffice

## Environment

- Venv: `~/pyenvs/maoffice/` — always use this, never venv inside repo
- `python3-venv` may not be installed; if `python3 -m venv` fails: `python3 -m venv --without-pip ~/pyenvs/maoffice && curl -k -sS https://bootstrap.pypa.io/get-pip.py | ~/pyenvs/maoffice/bin/python3`
- SSL quirk: `curl` needs `-k`; pip needs `--trusted-host pypi.org --trusted-host files.pythonhosted.org`
- Run scripts from repo root: `cd ~/git/maoffice && ~/pyenvs/maoffice/bin/python scripts/send_morning.py`

## Testing

- Always test CLI scripts before handoff — scripts must exit 1 and surface errors, never swallow exceptions
- After testing, clean up any temp files created (e.g. `.env.test`) — don't leave debris in the repo
- `.env` is gitignored; `.env.example` is the template — scripts validate its presence and required vars on startup
- With placeholder token in `.env`, scripts should reach Slack and fail with `invalid_auth` (confirms networking + code path works)

## Architecture

- `scheduler.py` holds placeholder data (Phase 1) and the two job functions (`send_morning_message`, `send_daily_summary`)
- `scripts/send_*.py` are manual one-shot triggers that load `.env` explicitly by repo-root path
- Local AI server at `http://localhost:4141/v1` (OpenAI-compatible); model set via `AI_MODEL` env var

## OpenDental Database

- **NEVER issue UPDATE or DELETE against the OpenDental database** — read-only access only
- OpenDental MySQL at `OD_MYSQL_HOST` (Windows Server, port 3306); credentials in `.env`
- Insurance join chain: `patient → patplan (Ordinal=1) → inssub → insplan → carrier` — `patient` table has NO `PriPlanNum` column
- Aging buckets: `Bal_0_30`, `Bal_31_60`, `Bal_61_90`, `BalOver90` (4 buckets — no `Bal_91_120` or `BalOver120`)
- Provider working schedule: `schedule` table `SchedType=1` (working blocks); `SchedType=0` = office-closed markers (ancient, ignore); `SchedType=2` = blockouts
- Hygiene appointments: booked under primary provider (`appointment.ProvNum`) but hygienist is in `appointment.ProvHyg` — always check both when counting appointments per provider
- All queries use PyMySQL DictCursor; connections opened per-query, closed immediately (no pool)
