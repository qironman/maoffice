# OpenDental Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Phase 1 placeholder data with live OpenDental MySQL queries and add a Slack `/od` slash command chatbot.

**Architecture:** Direct PyMySQL connection from Linux to the on-prem Windows Server MySQL (port 3306, same LAN). `maoffice/opendental.py` is a pure-SQL query layer. `maoffice/slack_bot.py` is a Slack Bolt Socket Mode app that runs as a thread alongside the existing APScheduler daemon.

**Tech Stack:** PyMySQL, slack-bolt, existing APScheduler + slack-sdk stack.

---

## Environment Notes

- Venv: `~/pyenvs/maoffice/` — always use this
- Install packages: `~/pyenvs/maoffice/bin/pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org <pkg>`
- Run from repo root: `cd ~/git/maoffice`
- `.env` file holds credentials — never commit it
- After editing code, restart systemd service: `systemctl --user restart maoffice`
- OpenDental MySQL: host from `OD_MYSQL_HOST` env var, user `root`, empty password, db `opendental`

---

## Task 1: Install dependencies and update requirements

**Files:**
- Modify: `requirements.txt`

**Step 1: Install new packages**

```bash
cd ~/git/maoffice
~/pyenvs/maoffice/bin/pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org PyMySQL slack-bolt
```

Expected: Both packages install without error.

**Step 2: Update requirements.txt**

Replace the file contents with:

```
slack-sdk>=3.27
slack-bolt>=1.18
apscheduler>=3.10
python-dotenv>=1.0
requests>=2.31
openai>=1.0
PyMySQL>=1.1
```

**Step 3: Verify import works**

```bash
~/pyenvs/maoffice/bin/python -c "import pymysql; import slack_bolt; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add PyMySQL and slack-bolt for Phase 2"
```

---

## Task 2: Update .env.example with new variables

**Files:**
- Modify: `.env.example`

**Step 1: Update .env.example**

Replace the file with:

```
SLACK_BOT_TOKEN=xoxb-...          # Bot OAuth token from Slack app settings
SLACK_APP_TOKEN=xapp-...          # App-level token for Socket Mode (starts with xapp-)
SLACK_CHANNEL_ID=C...             # Target channel ID (right-click channel → Copy ID)
DR_MA_USER_ID=U...                # Dr Ma's Slack user ID (for @mentions)
MORNING_TODO_TIME=08:00           # HH:MM in local time
DAILY_SUMMARY_TIME=18:00
TIMEZONE=America/Los_Angeles
AI_BASE_URL=http://localhost:4141/v1
AI_MODEL=llama3                   # or whatever model is running locally
OD_MYSQL_HOST=                    # IP of Windows Server running OpenDental
OD_MYSQL_PORT=3306
OD_MYSQL_USER=root
OD_MYSQL_PASSWORD=                # leave blank — default OD install has no password
OD_MYSQL_DB=opendental
```

**Step 2: Also add the new variables to your live .env**

```bash
# Edit ~/git/maoffice/.env and add:
# OD_MYSQL_HOST=<actual windows server IP>
# OD_MYSQL_PORT=3306
# OD_MYSQL_USER=root
# OD_MYSQL_PASSWORD=
# OD_MYSQL_DB=opendental
# SLACK_APP_TOKEN=<xapp-... from Slack app settings>
```

**Step 3: Commit**

```bash
git add .env.example
git commit -m "config: add OD_MYSQL_* and SLACK_APP_TOKEN to .env.example"
```

---

## Task 3: Create maoffice/opendental.py — MySQL connection helper

**Files:**
- Create: `maoffice/opendental.py`
- Create: `tests/test_opendental_connection.py`

**Step 1: Write the failing connection test**

Create `tests/test_opendental_connection.py`:

```python
"""Tests for opendental.py — uses unittest.mock to avoid needing a real DB."""
import os
from unittest.mock import MagicMock, patch

import pytest


def test_get_connection_uses_env_vars(monkeypatch):
    """get_connection() should read host/port/user/password/db from env."""
    monkeypatch.setenv("OD_MYSQL_HOST", "192.168.1.100")
    monkeypatch.setenv("OD_MYSQL_PORT", "3306")
    monkeypatch.setenv("OD_MYSQL_USER", "root")
    monkeypatch.setenv("OD_MYSQL_PASSWORD", "")
    monkeypatch.setenv("OD_MYSQL_DB", "opendental")

    with patch("pymysql.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        from maoffice import opendental
        opendental.get_connection()
        mock_connect.assert_called_once_with(
            host="192.168.1.100",
            port=3306,
            user="root",
            password="",
            database="opendental",
            connect_timeout=5,
            cursorclass=mock_connect.call_args.kwargs["cursorclass"],
        )


def test_get_connection_raises_when_host_missing(monkeypatch):
    """get_connection() should raise ValueError if OD_MYSQL_HOST is not set."""
    monkeypatch.delenv("OD_MYSQL_HOST", raising=False)
    # Force module reload so env changes take effect
    import importlib
    from maoffice import opendental
    importlib.reload(opendental)
    with pytest.raises(ValueError, match="OD_MYSQL_HOST"):
        opendental.get_connection()
```

**Step 2: Run test to verify it fails**

```bash
cd ~/git/maoffice
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_connection.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'maoffice.opendental'`

**Step 3: Create maoffice/opendental.py with get_connection()**

```python
"""OpenDental MySQL query layer.

All functions open a fresh connection, run the query, close the connection.
No persistent pool — queries are low-frequency (a few times per day).
"""

import os
from typing import Any

import pymysql
import pymysql.cursors


def get_connection() -> pymysql.connections.Connection:
    """Return a new PyMySQL connection using environment variables.

    Required env vars:
        OD_MYSQL_HOST, OD_MYSQL_PORT, OD_MYSQL_USER,
        OD_MYSQL_PASSWORD, OD_MYSQL_DB

    Raises:
        ValueError: If OD_MYSQL_HOST is not set.
        pymysql.Error: If the connection fails.
    """
    host = os.environ.get("OD_MYSQL_HOST")
    if not host:
        raise ValueError("OD_MYSQL_HOST is not set in environment")

    return pymysql.connect(
        host=host,
        port=int(os.environ.get("OD_MYSQL_PORT", "3306")),
        user=os.environ.get("OD_MYSQL_USER", "root"),
        password=os.environ.get("OD_MYSQL_PASSWORD", ""),
        database=os.environ.get("OD_MYSQL_DB", "opendental"),
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
    )
```

**Step 4: Run tests to verify they pass**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_connection.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add maoffice/opendental.py tests/test_opendental_connection.py
git commit -m "feat: add opendental.get_connection() with env-var config"
```

---

## Task 4: Add get_today_schedule() to opendental.py

**Files:**
- Modify: `maoffice/opendental.py`
- Create: `tests/test_opendental_schedule.py`

**Step 1: Write the failing test**

Create `tests/test_opendental_schedule.py`:

```python
"""Tests for get_today_schedule()."""
from datetime import date
from unittest.mock import MagicMock, patch

from maoffice import opendental


def _make_conn(rows):
    """Return a mock connection whose cursor fetchall() returns rows."""
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_today_schedule_returns_list():
    """get_today_schedule() should return a list of dicts."""
    fake_rows = [
        {
            "AptNum": 1,
            "AptDateTime": "2026-03-09 09:00:00",
            "PatientName": "Jane Doe",
            "ProvAbbr": "DR",
            "AptStatus": 1,
            "ProcDescript": "Cleaning",
        }
    ]
    conn, cursor = _make_conn(fake_rows)
    with patch.object(opendental, "get_connection", return_value=conn):
        result = opendental.get_today_schedule()
    assert isinstance(result, list)
    assert result[0]["PatientName"] == "Jane Doe"


def test_get_today_schedule_queries_today(monkeypatch):
    """get_today_schedule() should filter by today's date."""
    conn, cursor = _make_conn([])
    with patch.object(opendental, "get_connection", return_value=conn):
        opendental.get_today_schedule()
    sql_called = cursor.execute.call_args[0][0]
    assert "AptDateTime" in sql_called
    # Verify today's date string appears in the params
    params = cursor.execute.call_args[0][1]
    today_str = date.today().strftime("%Y-%m-%d")
    assert today_str in str(params)
```

**Step 2: Run test to verify it fails**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_schedule.py -v
```

Expected: FAIL — `AttributeError: module 'maoffice.opendental' has no attribute 'get_today_schedule'`

**Step 3: Add get_today_schedule() to opendental.py**

Append to `maoffice/opendental.py`:

```python

# ---------------------------------------------------------------------------
# AptStatus codes in OpenDental:
#   0 = Scheduled, 1 = Complete, 2 = UnschedList, 3 = ASAP, 5 = Broken
# ---------------------------------------------------------------------------
APT_STATUS = {0: "Scheduled", 1: "Complete", 2: "Unscheduled", 3: "ASAP", 5: "Broken"}


def get_today_schedule() -> list[dict[str, Any]]:
    """Return today's appointments ordered by time.

    Returns list of dicts with keys:
        AptNum, AptDateTime, PatientName, ProvAbbr, AptStatus, ProcDescript
    """
    today = __import__("datetime").date.today().strftime("%Y-%m-%d")
    sql = """
        SELECT
            a.AptNum,
            a.AptDateTime,
            CONCAT(p.LName, ', ', p.FName) AS PatientName,
            pr.Abbr AS ProvAbbr,
            a.AptStatus,
            a.ProcDescript
        FROM appointment a
        JOIN patient p ON p.PatNum = a.PatNum
        LEFT JOIN provider pr ON pr.ProvNum = a.ProvNum
        WHERE DATE(a.AptDateTime) = %s
          AND a.AptStatus NOT IN (2, 5)
        ORDER BY a.AptDateTime
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (today,))
            return cur.fetchall()


def get_today_cancellations() -> list[dict[str, Any]]:
    """Return today's broken/unscheduled appointments."""
    today = __import__("datetime").date.today().strftime("%Y-%m-%d")
    sql = """
        SELECT
            a.AptNum,
            a.AptDateTime,
            CONCAT(p.LName, ', ', p.FName) AS PatientName,
            a.AptStatus,
            a.ProcDescript
        FROM appointment a
        JOIN patient p ON p.PatNum = a.PatNum
        WHERE DATE(a.AptDateTime) = %s
          AND a.AptStatus IN (2, 5)
        ORDER BY a.AptDateTime
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (today,))
            return cur.fetchall()
```

**Step 4: Run tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_schedule.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add maoffice/opendental.py tests/test_opendental_schedule.py
git commit -m "feat: add get_today_schedule() and get_today_cancellations()"
```

---

## Task 5: Add get_open_slots() for next 7 days

**Files:**
- Modify: `maoffice/opendental.py`
- Create: `tests/test_opendental_slots.py`

**Step 1: Write the failing test**

Create `tests/test_opendental_slots.py`:

```python
"""Tests for get_open_slots()."""
from unittest.mock import MagicMock, patch

from maoffice import opendental


def _make_conn(rows):
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_open_slots_returns_list():
    """get_open_slots() returns a list of dicts with date and count."""
    fake_rows = [
        {"SchedDate": "2026-03-10", "ProvAbbr": "DR", "OpenSlots": 3},
    ]
    conn, _ = _make_conn(fake_rows)
    with patch.object(opendental, "get_connection", return_value=conn):
        result = opendental.get_open_slots()
    assert isinstance(result, list)
    assert result[0]["OpenSlots"] == 3


def test_get_open_slots_queries_next_7_days(monkeypatch):
    """get_open_slots() should query 7 days out from today."""
    conn, cursor = _make_conn([])
    with patch.object(opendental, "get_connection", return_value=conn):
        opendental.get_open_slots()
    params = cursor.execute.call_args[0][1]
    # Should pass two date params (start, end)
    assert len(params) == 2
```

**Step 2: Run test to verify it fails**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_slots.py -v
```

Expected: FAIL

**Step 3: Add get_open_slots() to opendental.py**

Append to `maoffice/opendental.py`:

```python

def get_open_slots(days_ahead: int = 7) -> list[dict[str, Any]]:
    """Return open appointment slots for the next N days grouped by date + provider.

    OpenDental tracks available blocks in the `schedule` table. An open slot
    is a scheduled block with no appointment booked against it.
    Returns list of dicts: {SchedDate, ProvAbbr, OpenSlots}
    """
    from datetime import date, timedelta
    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    sql = """
        SELECT
            DATE(s.SchedDate) AS SchedDate,
            pr.Abbr AS ProvAbbr,
            COUNT(*) AS OpenSlots
        FROM schedule s
        LEFT JOIN provider pr ON pr.ProvNum = s.ProvNum
        WHERE s.SchedDate >= %s
          AND s.SchedDate < %s
          AND s.Status = 0
          AND s.SchedType = 0
          AND NOT EXISTS (
              SELECT 1 FROM appointment a
              WHERE a.ProvNum = s.ProvNum
                AND DATE(a.AptDateTime) = DATE(s.SchedDate)
                AND a.AptStatus NOT IN (2, 5)
          )
        GROUP BY DATE(s.SchedDate), s.ProvNum
        ORDER BY SchedDate, ProvAbbr
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (today.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
            return cur.fetchall()
```

**Step 4: Run tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_slots.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add maoffice/opendental.py tests/test_opendental_slots.py
git commit -m "feat: add get_open_slots() for next-7-days open schedule"
```

---

## Task 6: Add get_daily_production() and get_collections()

**Files:**
- Modify: `maoffice/opendental.py`
- Create: `tests/test_opendental_production.py`

**Step 1: Write the failing test**

Create `tests/test_opendental_production.py`:

```python
"""Tests for get_daily_production() and get_collections()."""
from unittest.mock import MagicMock, patch

from maoffice import opendental


def _make_conn(rows):
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = rows
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_daily_production_returns_dict():
    """get_daily_production() returns dict with production and procedure_count."""
    fake_row = {"production": 4200.0, "procedure_count": 15}
    conn, _ = _make_conn(fake_row)
    with patch.object(opendental, "get_connection", return_value=conn):
        result = opendental.get_daily_production()
    assert "production" in result
    assert "procedure_count" in result


def test_get_collections_returns_dict():
    """get_collections() returns dict with patient_payments and insurance_payments."""
    fake_row = {"patient_payments": 1200.0, "insurance_payments": 2600.0}
    conn, _ = _make_conn(fake_row)
    with patch.object(opendental, "get_connection", return_value=conn):
        result = opendental.get_collections()
    assert "patient_payments" in result
    assert "insurance_payments" in result
```

**Step 2: Run test to verify it fails**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_production.py -v
```

Expected: FAIL

**Step 3: Add get_daily_production() and get_collections() to opendental.py**

Append to `maoffice/opendental.py`:

```python

def get_daily_production() -> dict[str, Any]:
    """Return today's production: total fee and procedure count.

    Returns dict: {production: float, procedure_count: int}
    """
    today = __import__("datetime").date.today().strftime("%Y-%m-%d")
    sql = """
        SELECT
            COALESCE(SUM(pl.ProcFee), 0) AS production,
            COUNT(*) AS procedure_count
        FROM procedurelog pl
        WHERE DATE(pl.ProcDate) = %s
          AND pl.ProcStatus = 2
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (today,))
            row = cur.fetchone()
            return row or {"production": 0.0, "procedure_count": 0}


def get_collections() -> dict[str, Any]:
    """Return today's collections split by patient and insurance.

    Returns dict: {patient_payments: float, insurance_payments: float}
    """
    today = __import__("datetime").date.today().strftime("%Y-%m-%d")

    patient_sql = """
        SELECT COALESCE(SUM(PayAmt), 0) AS patient_payments
        FROM payment
        WHERE DATE(PayDate) = %s
    """
    insurance_sql = """
        SELECT COALESCE(SUM(InsPayAmt), 0) AS insurance_payments
        FROM claimproc
        WHERE DATE(DateCP) = %s
          AND Status = 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(patient_sql, (today,))
            pat = cur.fetchone() or {}
            cur.execute(insurance_sql, (today,))
            ins = cur.fetchone() or {}
    return {
        "patient_payments": float(pat.get("patient_payments", 0)),
        "insurance_payments": float(ins.get("insurance_payments", 0)),
    }
```

**Step 4: Run tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_production.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add maoffice/opendental.py tests/test_opendental_production.py
git commit -m "feat: add get_daily_production() and get_collections()"
```

---

## Task 7: Add get_aging_report() and find_patients()

**Files:**
- Modify: `maoffice/opendental.py`
- Create: `tests/test_opendental_aging.py`

**Step 1: Write the failing test**

Create `tests/test_opendental_aging.py`:

```python
"""Tests for get_aging_report() and find_patients()."""
from unittest.mock import MagicMock, patch

from maoffice import opendental


def _make_conn_fetchone(row):
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = row
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn


def _make_conn_fetchall(rows):
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn


def test_get_aging_report_returns_buckets():
    """get_aging_report() returns dict with 30/60/90/120+ buckets."""
    fake_row = {"bal_0_30": 500.0, "bal_31_60": 200.0, "bal_61_90": 100.0, "bal_91_120": 50.0, "bal_over_120": 25.0}
    conn = _make_conn_fetchone(fake_row)
    with patch.object(opendental, "get_connection", return_value=conn):
        result = opendental.get_aging_report()
    assert "bal_0_30" in result
    assert "bal_over_120" in result


def test_find_patients_returns_list():
    """find_patients() returns a list of matching patients."""
    fake_rows = [
        {"PatNum": 42, "LName": "Doe", "FName": "Jane", "Birthdate": "1985-06-15",
         "BalTotal": 150.0, "NextAptDate": "2026-04-01", "PriCarrier": "Delta Dental"}
    ]
    conn = _make_conn_fetchall(fake_rows)
    with patch.object(opendental, "get_connection", return_value=conn):
        result = opendental.find_patients("doe")
    assert len(result) == 1
    assert result[0]["LName"] == "Doe"


def test_find_patients_search_is_case_insensitive():
    """find_patients() should match regardless of case."""
    conn = _make_conn_fetchall([])
    with patch.object(opendental, "get_connection", return_value=conn):
        opendental.find_patients("DOE")
    # Should not raise
```

**Step 2: Run test to verify it fails**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_aging.py -v
```

Expected: FAIL

**Step 3: Add get_aging_report() and find_patients() to opendental.py**

Append to `maoffice/opendental.py`:

```python

def get_aging_report() -> dict[str, Any]:
    """Return AR aging buckets across all patients with outstanding balances.

    OpenDental stores pre-computed aging in the patient table.
    Returns dict: {bal_0_30, bal_31_60, bal_61_90, bal_91_120, bal_over_120}
    all as floats.
    """
    sql = """
        SELECT
            COALESCE(SUM(Bal_0_30), 0)   AS bal_0_30,
            COALESCE(SUM(Bal_31_60), 0)  AS bal_31_60,
            COALESCE(SUM(Bal_61_90), 0)  AS bal_61_90,
            COALESCE(SUM(Bal_91_120), 0) AS bal_91_120,
            COALESCE(SUM(BalOver120), 0) AS bal_over_120
        FROM patient
        WHERE BalTotal > 0
          AND PatStatus = 0
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row or {
                "bal_0_30": 0.0, "bal_31_60": 0.0, "bal_61_90": 0.0,
                "bal_91_120": 0.0, "bal_over_120": 0.0,
            }


def get_insurance_claims_summary() -> dict[str, Any]:
    """Return count and total of pending and rejected insurance claims.

    Returns dict: {pending_count, pending_total, rejected_count, rejected_total}
    ClaimStatus: 0=Unsent, 1=Sent, 4=Received, 5=Preauth, 6=Supplemental
    claimproc Status: 0=NotReceived, 1=Received, 2=Preauth, 3=Adjustment
    """
    sql = """
        SELECT
            SUM(CASE WHEN c.ClaimStatus = 1 THEN 1 ELSE 0 END)             AS pending_count,
            COALESCE(SUM(CASE WHEN c.ClaimStatus = 1 THEN c.ClaimFee END), 0) AS pending_total,
            SUM(CASE WHEN c.ClaimStatus = 7 THEN 1 ELSE 0 END)             AS rejected_count,
            COALESCE(SUM(CASE WHEN c.ClaimStatus = 7 THEN c.ClaimFee END), 0) AS rejected_total
        FROM claim c
        WHERE c.DateService >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row or {
                "pending_count": 0, "pending_total": 0.0,
                "rejected_count": 0, "rejected_total": 0.0,
            }


def find_patients(search: str) -> list[dict[str, Any]]:
    """Search patients by last name (case-insensitive, partial match).

    Returns list of dicts with keys:
        PatNum, LName, FName, Birthdate, BalTotal, NextAptDate, PriCarrier
    """
    sql = """
        SELECT
            p.PatNum,
            p.LName,
            p.FName,
            p.Birthdate,
            p.BalTotal,
            (SELECT MIN(a.AptDateTime)
             FROM appointment a
             WHERE a.PatNum = p.PatNum
               AND a.AptDateTime >= NOW()
               AND a.AptStatus = 0) AS NextAptDate,
            ic.CarrierName AS PriCarrier
        FROM patient p
        LEFT JOIN insplan ip ON ip.PlanNum = p.PriPlanNum
        LEFT JOIN carrier ic ON ic.CarrierNum = ip.CarrierNum
        WHERE p.LName LIKE %s
          AND p.PatStatus = 0
        ORDER BY p.LName, p.FName
        LIMIT 10
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (f"%{search}%",))
            return cur.fetchall()
```

**Step 4: Run tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_opendental_aging.py -v
```

Expected: 3 PASSED

**Step 5: Run all tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/ -v
```

Expected: All PASSED

**Step 6: Commit**

```bash
git add maoffice/opendental.py tests/test_opendental_aging.py
git commit -m "feat: add get_aging_report(), get_insurance_claims_summary(), find_patients()"
```

---

## Task 8: Update messages.py — add new message formatters

**Files:**
- Modify: `maoffice/messages.py`
- Create: `tests/test_messages_v2.py`

**Step 1: Write the failing test**

Create `tests/test_messages_v2.py`:

```python
"""Tests for new message formatters added in Phase 2."""
from maoffice import messages


def test_build_morning_message_with_schedule():
    """build_morning_message() should include schedule and open slots sections."""
    schedule = [
        {"AptDateTime": "2026-03-09 09:00:00", "PatientName": "Doe, Jane",
         "ProvAbbr": "DR", "ProcDescript": "Cleaning"},
    ]
    cancellations = []
    open_slots = [{"SchedDate": "2026-03-10", "ProvAbbr": "DR", "OpenSlots": 2}]

    text, blocks = messages.build_morning_message_v2(schedule, cancellations, open_slots)

    assert "Doe, Jane" in text or any(
        "Doe, Jane" in str(b) for b in blocks
    )
    assert isinstance(blocks, list)
    assert len(blocks) > 0


def test_build_summary_message_with_stats():
    """build_summary_message_v2() should format production + aging."""
    production = {"production": 4200.0, "procedure_count": 15}
    collections = {"patient_payments": 1200.0, "insurance_payments": 2600.0}
    aging = {"bal_0_30": 500.0, "bal_31_60": 200.0, "bal_61_90": 100.0,
             "bal_91_120": 50.0, "bal_over_120": 25.0}
    claims = {"pending_count": 3, "pending_total": 1800.0,
              "rejected_count": 1, "rejected_total": 600.0}
    cancellations = [{"PatientName": "Smith, Bob", "ProcDescript": "Crown"}]
    ai_summary = "Great day! 15 procedures completed."

    text, blocks = messages.build_summary_message_v2(
        ai_summary, production, collections, aging, claims, cancellations
    )

    assert "$4,200" in text or "$4200" in text or "4200" in str(blocks)
    assert isinstance(blocks, list)
```

**Step 2: Run test to verify it fails**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_messages_v2.py -v
```

Expected: FAIL

**Step 3: Add new formatter functions to messages.py**

Append to `maoffice/messages.py`:

```python

def _fmt_currency(amount) -> str:
    """Format a float as currency string, e.g. 4200.0 → '$4,200'."""
    return f"${float(amount):,.0f}"


def build_morning_message_v2(
    schedule: list[dict],
    cancellations: list[dict],
    open_slots: list[dict],
) -> tuple[str, list[dict]]:
    """Build the Phase 2 morning message with live OpenDental data.

    Args:
        schedule: List of today's appointments from opendental.get_today_schedule().
        cancellations: Today's broken/unscheduled from opendental.get_today_cancellations().
        open_slots: Next-7-days open slots from opendental.get_open_slots().

    Returns:
        Tuple of (plain_text_fallback, blocks).
    """
    from datetime import date
    today = date.today().strftime("%A, %B %-d, %Y")
    mention = _dr_ma_mention()

    # Build plain text
    apt_lines = "\n".join(
        f"• {a['AptDateTime'][11:16]}  {a['PatientName']}  [{a.get('ProvAbbr', '')}]  {a.get('ProcDescript', '')}"
        for a in schedule
    ) or "• No appointments scheduled today."

    slot_lines = "\n".join(
        f"• {s['SchedDate']}  {s.get('ProvAbbr', '')}  — {s['OpenSlots']} open slot(s)"
        for s in open_slots
    ) or "• Schedule is full this week."

    cancel_lines = "\n".join(
        f"• {c['PatientName']}  {c.get('ProcDescript', '')}"
        for c in cancellations
    ) or "• None"

    plain_text = (
        f"{mention} 🌅 Good morning! Here's your schedule for {today}:\n"
        f"{apt_lines}\n\n"
        f"Cancellations today:\n{cancel_lines}\n\n"
        f"Open slots next 7 days:\n{slot_lines}"
    )

    # Build blocks
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{mention} 🌅 *Good morning!*"}},
        {"type": "header", "text": {"type": "plain_text", "text": f"Schedule — {today}", "emoji": True}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Today's Appointments ({len(schedule)})*\n{apt_lines}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Cancellations / No-shows*\n{cancel_lines}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Open Slots — Next 7 Days*\n{slot_lines}"}},
        {"type": "divider"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Have a great day! 😊"}]},
    ]

    return plain_text, blocks


def build_summary_message_v2(
    ai_summary: str,
    production: dict,
    collections: dict,
    aging: dict,
    claims: dict,
    cancellations: list[dict],
) -> tuple[str, list[dict]]:
    """Build the Phase 2 evening summary with live OpenDental data.

    Returns:
        Tuple of (plain_text_fallback, blocks).
    """
    from datetime import date
    today = date.today().strftime("%A, %B %-d, %Y")
    mention = _dr_ma_mention()

    prod = _fmt_currency(production.get("production", 0))
    proc_count = production.get("procedure_count", 0)
    pat_pay = _fmt_currency(collections.get("patient_payments", 0))
    ins_pay = _fmt_currency(collections.get("insurance_payments", 0))
    total_collect = _fmt_currency(
        float(collections.get("patient_payments", 0)) + float(collections.get("insurance_payments", 0))
    )

    aging_text = (
        f"*AR Aging:* "
        f"0-30: {_fmt_currency(aging.get('bal_0_30', 0))} | "
        f"31-60: {_fmt_currency(aging.get('bal_31_60', 0))} | "
        f"61-90: {_fmt_currency(aging.get('bal_61_90', 0))} | "
        f"91-120: {_fmt_currency(aging.get('bal_91_120', 0))} | "
        f"120+: {_fmt_currency(aging.get('bal_over_120', 0))}"
    )

    cancel_lines = "\n".join(
        f"• {c['PatientName']}  {c.get('ProcDescript', '')}" for c in cancellations
    ) or "• None"

    plain_text = (
        f"{mention} 📋 Daily Summary — {today}\n"
        f"Production: {prod} ({proc_count} procedures)\n"
        f"Collections: {total_collect} (patient: {pat_pay} | insurance: {ins_pay})\n"
        f"Pending claims: {claims.get('pending_count', 0)} ({_fmt_currency(claims.get('pending_total', 0))})\n\n"
        f"{ai_summary}"
    )

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{mention} 📋 *Daily Summary*"}},
        {"type": "header", "text": {"type": "plain_text", "text": f"Daily Summary — {today}", "emoji": True}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*Production:* {prod}  ({proc_count} procedures)\n"
            f"*Collections:* {total_collect}  (patient: {pat_pay} | insurance: {ins_pay})"
        )}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": aging_text}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*Claims:* {claims.get('pending_count', 0)} pending ({_fmt_currency(claims.get('pending_total', 0))}) | "
            f"{claims.get('rejected_count', 0)} rejected ({_fmt_currency(claims.get('rejected_total', 0))})"
        )}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Cancellations / No-shows:*\n{cancel_lines}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*AI Summary:*\n{ai_summary}"}},
        {"type": "divider"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Generated by maoffice 🤖"}]},
    ]

    return plain_text, blocks
```

**Step 4: Run tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_messages_v2.py -v
```

Expected: 2 PASSED

**Step 5: Run all tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/ -v
```

Expected: All PASSED

**Step 6: Commit**

```bash
git add maoffice/messages.py tests/test_messages_v2.py
git commit -m "feat: add build_morning_message_v2() and build_summary_message_v2() with live data"
```

---

## Task 9: Update scheduler.py to use real OpenDental data

**Files:**
- Modify: `maoffice/scheduler.py`

**Step 1: Replace scheduler.py**

Replace the entire `maoffice/scheduler.py` with:

```python
"""APScheduler-based scheduler for morning and evening Slack notifications."""

import logging
import os
from datetime import date

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from maoffice import ai_summary, messages, opendental, slack_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------


def send_morning_message() -> None:
    """Fetch live OpenDental data and send morning schedule to Slack."""
    channel = os.environ["SLACK_CHANNEL_ID"]
    try:
        schedule = opendental.get_today_schedule()
        cancellations = opendental.get_today_cancellations()
        open_slots = opendental.get_open_slots()
    except Exception:
        logger.exception("Failed to query OpenDental — sending warning to Slack")
        slack_client.send_message(
            channel,
            "⚠️ maoffice: Could not reach OpenDental DB for morning report. Please check the connection.",
        )
        return

    try:
        plain_text, blocks = messages.build_morning_message_v2(schedule, cancellations, open_slots)
        slack_client.send_message(channel, plain_text, blocks)
        logger.info("Morning message sent to %s (%d appointments)", channel, len(schedule))
    except Exception:
        logger.exception("Failed to send morning message")


def send_daily_summary() -> None:
    """Fetch live OpenDental data, generate AI summary, send to Slack."""
    channel = os.environ["SLACK_CHANNEL_ID"]

    # Query OpenDental
    try:
        production = opendental.get_daily_production()
        collections = opendental.get_collections()
        claims = opendental.get_insurance_claims_summary()
        cancellations = opendental.get_today_cancellations()

        # AR aging: only on Mondays (or always — configurable via env)
        if date.today().weekday() == 0 or os.environ.get("AGING_DAILY", "").lower() == "true":
            aging = opendental.get_aging_report()
        else:
            aging = {"bal_0_30": 0.0, "bal_31_60": 0.0, "bal_61_90": 0.0,
                     "bal_91_120": 0.0, "bal_over_120": 0.0}

    except Exception:
        logger.exception("Failed to query OpenDental — sending warning to Slack")
        slack_client.send_message(
            channel,
            "⚠️ maoffice: Could not reach OpenDental DB for daily summary. Please check the connection.",
        )
        return

    # Build raw text for AI summarization
    raw_text = (
        f"Date: {date.today().isoformat()}. "
        f"Procedures completed: {production['procedure_count']}, "
        f"Production: ${production['production']:,.0f}, "
        f"Patient payments: ${collections['patient_payments']:,.0f}, "
        f"Insurance payments: ${collections['insurance_payments']:,.0f}. "
        f"Cancellations/no-shows: {len(cancellations)}. "
        f"Pending insurance claims: {claims['pending_count']} totaling ${claims['pending_total']:,.0f}. "
        f"AR over 90 days: ${float(aging.get('bal_91_120', 0)) + float(aging.get('bal_over_120', 0)):,.0f}."
    )

    try:
        ai_text = ai_summary.summarize(raw_text)
    except Exception:
        logger.exception("AI summary failed; using raw text")
        ai_text = raw_text

    try:
        plain_text, blocks = messages.build_summary_message_v2(
            ai_text, production, collections, aging, claims, cancellations
        )
        slack_client.send_message(channel, plain_text, blocks)
        logger.info("Daily summary sent to %s", channel)
    except Exception:
        logger.exception("Failed to send daily summary")


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------


def _parse_time(env_var: str, default: str) -> tuple[int, int]:
    """Parse 'HH:MM' from an env var."""
    value = os.environ.get(env_var, default)
    try:
        h, m = value.split(":")
        return int(h), int(m)
    except ValueError:
        logger.warning("Invalid time format for %s='%s'; using default %s", env_var, value, default)
        h, m = default.split(":")
        return int(h), int(m)


def create_scheduler() -> BlockingScheduler:
    """Create and configure the BlockingScheduler with morning + evening jobs."""
    timezone = os.environ.get("TIMEZONE", "America/Los_Angeles")

    morning_h, morning_m = _parse_time("MORNING_TODO_TIME", "08:00")
    summary_h, summary_m = _parse_time("DAILY_SUMMARY_TIME", "18:00")

    scheduler = BlockingScheduler(timezone=timezone)

    scheduler.add_job(
        send_morning_message,
        trigger=CronTrigger(hour=morning_h, minute=morning_m, timezone=timezone),
        id="morning_todo",
        name="Morning schedule",
        replace_existing=True,
    )

    scheduler.add_job(
        send_daily_summary,
        trigger=CronTrigger(hour=summary_h, minute=summary_m, timezone=timezone),
        id="daily_summary",
        name="Daily summary",
        replace_existing=True,
    )

    logger.info(
        "Scheduled morning at %02d:%02d and summary at %02d:%02d (%s)",
        morning_h, morning_m, summary_h, summary_m, timezone,
    )

    return scheduler


def run() -> None:
    """Start the blocking scheduler (runs forever)."""
    scheduler = create_scheduler()
    logger.info("Starting maoffice scheduler…")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
```

**Step 2: Run all tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/ -v
```

Expected: All PASSED (scheduler.py changes don't break existing tests since job functions are integration-tested via opendental mocks)

**Step 3: Commit**

```bash
git add maoffice/scheduler.py
git commit -m "feat: wire scheduler to live OpenDental data (Phase 2)"
```

---

## Task 10: Create maoffice/slack_bot.py — Slack Bolt slash command handler

**Files:**
- Create: `maoffice/slack_bot.py`
- Create: `tests/test_slack_bot.py`

**Background:** Slack Bolt Socket Mode requires two tokens:
- `SLACK_BOT_TOKEN` (already in .env) — `xoxb-...` for posting messages
- `SLACK_APP_TOKEN` (new) — `xapp-...` for maintaining the Socket Mode WebSocket

The `/od` command must be registered in the Slack app settings at api.slack.com → your app → Slash Commands.

**Step 1: Write the failing test**

Create `tests/test_slack_bot.py`:

```python
"""Tests for slack_bot.py command parsing."""
from maoffice import slack_bot


def test_parse_od_command_schedule():
    assert slack_bot.parse_od_command("schedule") == ("schedule", "")


def test_parse_od_command_patient():
    assert slack_bot.parse_od_command("patient Jane Doe") == ("patient", "Jane Doe")


def test_parse_od_command_unknown():
    cmd, _ = slack_bot.parse_od_command("blah")
    assert cmd == "unknown"


def test_parse_od_command_empty():
    cmd, _ = slack_bot.parse_od_command("")
    assert cmd == "help"


def test_format_schedule_response_empty():
    text = slack_bot.format_schedule_response([], [])
    assert "No appointments" in text


def test_format_schedule_response_with_data():
    schedule = [
        {"AptDateTime": "2026-03-09 09:00:00", "PatientName": "Doe, Jane",
         "ProvAbbr": "DR", "ProcDescript": "Cleaning"}
    ]
    text = slack_bot.format_schedule_response(schedule, [])
    assert "Doe, Jane" in text


def test_format_patient_response_not_found():
    text = slack_bot.format_patient_response([], "Smith")
    assert "No patients found" in text


def test_format_aging_response():
    aging = {"bal_0_30": 500.0, "bal_31_60": 200.0, "bal_61_90": 100.0,
             "bal_91_120": 50.0, "bal_over_120": 25.0}
    text = slack_bot.format_aging_response(aging)
    assert "0-30" in text
    assert "$500" in text
```

**Step 2: Run test to verify it fails**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_slack_bot.py -v
```

Expected: FAIL

**Step 3: Create maoffice/slack_bot.py**

```python
"""Slack Bolt Socket Mode app for /od slash commands.

Runs as a thread alongside the APScheduler daemon.
Requires SLACK_APP_TOKEN (xapp-...) and SLACK_BOT_TOKEN in environment.
"""

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "*/od* commands:\n"
    "• `/od schedule` — Today's appointments\n"
    "• `/od patient <name>` — Look up a patient\n"
    "• `/od aging` — AR aging report\n"
    "• `/od production` — Today's production + collections\n"
    "• `/od openslots` — Open slots this week\n"
    "• `/od help` — This help message"
)


# ---------------------------------------------------------------------------
# Command parsing (pure functions — easy to test)
# ---------------------------------------------------------------------------


def parse_od_command(text: str) -> tuple[str, str]:
    """Parse '/od <subcommand> [args]' text.

    Returns (subcommand, args_string).
    """
    text = text.strip()
    if not text:
        return ("help", "")
    parts = text.split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    valid = {"schedule", "patient", "aging", "production", "openslots", "help"}
    if cmd not in valid:
        return ("unknown", text)
    return (cmd, args)


# ---------------------------------------------------------------------------
# Response formatters (pure functions — easy to test)
# ---------------------------------------------------------------------------


def format_schedule_response(schedule: list[dict], cancellations: list[dict]) -> str:
    if not schedule:
        lines = ["No appointments scheduled today."]
    else:
        lines = [f"*Today's Schedule ({len(schedule)} appointments):*"]
        for a in schedule:
            t = str(a.get("AptDateTime", ""))
            time_str = t[11:16] if len(t) >= 16 else t
            lines.append(
                f"• {time_str}  {a.get('PatientName', '')}  [{a.get('ProvAbbr', '')}]  {a.get('ProcDescript', '')}"
            )
    if cancellations:
        lines.append(f"\n*Cancellations ({len(cancellations)}):*")
        for c in cancellations:
            lines.append(f"• {c.get('PatientName', '')}  {c.get('ProcDescript', '')}")
    return "\n".join(lines)


def format_patient_response(patients: list[dict], search: str) -> str:
    if not patients:
        return f"No patients found matching _{search}_."
    lines = [f"*Patients matching '{search}':*"]
    for p in patients:
        next_apt = p.get("NextAptDate") or "none scheduled"
        lines.append(
            f"• *{p.get('LName')}, {p.get('FName')}*  "
            f"DOB: {str(p.get('Birthdate', ''))[:10]}  "
            f"Balance: ${float(p.get('BalTotal', 0)):,.0f}  "
            f"Insurance: {p.get('PriCarrier', 'none')}  "
            f"Next appt: {str(next_apt)[:16]}"
        )
    return "\n".join(lines)


def format_aging_response(aging: dict) -> str:
    total = sum(float(v) for v in aging.values())
    return (
        f"*AR Aging Report:*\n"
        f"• 0-30 days:   ${float(aging.get('bal_0_30', 0)):,.0f}\n"
        f"• 31-60 days:  ${float(aging.get('bal_31_60', 0)):,.0f}\n"
        f"• 61-90 days:  ${float(aging.get('bal_61_90', 0)):,.0f}\n"
        f"• 91-120 days: ${float(aging.get('bal_91_120', 0)):,.0f}\n"
        f"• 120+ days:   ${float(aging.get('bal_over_120', 0)):,.0f}\n"
        f"• *Total outstanding: ${total:,.0f}*"
    )


def format_production_response(production: dict, collections: dict) -> str:
    total_collect = float(collections.get("patient_payments", 0)) + float(collections.get("insurance_payments", 0))
    return (
        f"*Today's Production & Collections:*\n"
        f"• Production: ${float(production.get('production', 0)):,.0f} "
        f"({production.get('procedure_count', 0)} procedures)\n"
        f"• Collections: ${total_collect:,.0f} "
        f"(patient: ${float(collections.get('patient_payments', 0)):,.0f} | "
        f"insurance: ${float(collections.get('insurance_payments', 0)):,.0f})"
    )


def format_openslots_response(slots: list[dict]) -> str:
    if not slots:
        return "No open slots found in the next 7 days — schedule is full! 🎉"
    lines = ["*Open Slots — Next 7 Days:*"]
    for s in slots:
        lines.append(f"• {s.get('SchedDate', '')}  [{s.get('ProvAbbr', '')}]  {s.get('OpenSlots', 0)} slot(s)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bolt app (only imported when SLACK_APP_TOKEN is available)
# ---------------------------------------------------------------------------


def build_app():
    """Build and return the Slack Bolt App instance."""
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    from maoffice import opendental

    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    allowed_channel = os.environ.get("SLACK_CHANNEL_ID", "")

    @app.command("/od")
    def handle_od(ack, respond, command):
        ack()  # Must acknowledge within 3 seconds
        text = command.get("text", "")
        cmd, args = parse_od_command(text)

        try:
            if cmd == "help" or cmd == "unknown":
                respond(HELP_TEXT)

            elif cmd == "schedule":
                schedule = opendental.get_today_schedule()
                cancellations = opendental.get_today_cancellations()
                respond(format_schedule_response(schedule, cancellations))

            elif cmd == "patient":
                if not args:
                    respond("Usage: `/od patient <last name>`")
                    return
                patients = opendental.find_patients(args)
                respond(format_patient_response(patients, args))

            elif cmd == "aging":
                aging = opendental.get_aging_report()
                respond(format_aging_response(aging))

            elif cmd == "production":
                production = opendental.get_daily_production()
                collections = opendental.get_collections()
                respond(format_production_response(production, collections))

            elif cmd == "openslots":
                slots = opendental.get_open_slots()
                respond(format_openslots_response(slots))

        except Exception as e:
            logger.exception("Error handling /od %s", cmd)
            respond(f"⚠️ Error: could not complete request. ({type(e).__name__}: {e})")

    return app


def start_in_thread() -> threading.Thread:
    """Start the Slack Bolt Socket Mode handler in a daemon thread.

    Returns the thread (already started).
    Logs a warning and returns immediately if SLACK_APP_TOKEN is not set.
    """
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        logger.warning("SLACK_APP_TOKEN not set — Slack bot slash commands disabled")
        # Return a dummy thread that does nothing
        t = threading.Thread(target=lambda: None, daemon=True)
        t.start()
        return t

    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = build_app()
    handler = SocketModeHandler(app, app_token)

    def _run():
        logger.info("Starting Slack Bolt Socket Mode handler…")
        handler.start()

    t = threading.Thread(target=_run, daemon=True, name="slack-bolt")
    t.start()
    return t
```

**Step 4: Run tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/test_slack_bot.py -v
```

Expected: All PASSED (pure-function tests don't need Slack connection)

**Step 5: Run all tests**

```bash
~/pyenvs/maoffice/bin/python -m pytest tests/ -v
```

Expected: All PASSED

**Step 6: Commit**

```bash
git add maoffice/slack_bot.py tests/test_slack_bot.py
git commit -m "feat: add Slack Bolt Socket Mode /od slash command handler"
```

---

## Task 11: Update main.py to run bot + scheduler together

**Files:**
- Modify: `main.py`

**Step 1: Replace main.py**

```python
#!/usr/bin/env python3
"""Entry point for the maoffice daemon.

Starts two concurrent components:
1. Slack Bolt Socket Mode thread — handles /od slash commands
2. APScheduler blocking loop — sends morning + evening Slack messages
"""

import logging
import os

from dotenv import load_dotenv

# Load .env before importing any maoffice modules (they read env vars at import time)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from maoffice import slack_bot
from maoffice.scheduler import run

if __name__ == "__main__":
    # Start Slack bot in background thread (gracefully skipped if SLACK_APP_TOKEN unset)
    slack_bot.start_in_thread()
    # Run scheduler in foreground (blocks until Ctrl+C / systemd stop)
    run()
```

**Step 2: Verify it starts cleanly (with a fake env)**

```bash
cd ~/git/maoffice
# Quick syntax check
~/pyenvs/maoffice/bin/python -c "import ast; ast.parse(open('main.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: start Slack bot thread + scheduler in main.py"
```

---

## Task 12: Add setup_od_user.sql and update scripts

**Files:**
- Create: `scripts/setup_od_user.sql`
- Modify: `scripts/send_morning.py` (update to use v2 formatters)
- Modify: `scripts/send_summary.py` (update to use v2 formatters)

**Step 1: Create scripts/setup_od_user.sql**

```sql
-- Run this once on the OpenDental Windows Server MySQL as root
-- to create a read-only user for maoffice (optional hardening step).
--
-- Usage (from Windows cmd):
--   mysql -u root -e "source setup_od_user.sql"
--
-- Replace 192.168.1.x with the actual IP of your Linux machine.

CREATE USER IF NOT EXISTS 'maoffice_reader'@'192.168.1.%'
    IDENTIFIED BY 'choose-a-strong-password-here';

GRANT SELECT ON opendental.* TO 'maoffice_reader'@'192.168.1.%';

FLUSH PRIVILEGES;

SELECT 'maoffice_reader user created with SELECT on opendental.*' AS status;
```

**Step 2: Update scripts/send_morning.py to use live data**

Replace `scripts/send_morning.py` with:

```python
#!/usr/bin/env python3
"""Manual one-shot: send morning schedule message now."""

import os
import sys
from pathlib import Path

# Load .env from repo root
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / ".env")

from maoffice import opendental, messages, slack_client


def main():
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not channel:
        print("ERROR: SLACK_CHANNEL_ID not set", file=sys.stderr)
        sys.exit(1)

    od_host = os.environ.get("OD_MYSQL_HOST")
    if not od_host:
        print("ERROR: OD_MYSQL_HOST not set", file=sys.stderr)
        sys.exit(1)

    print(f"Querying OpenDental at {od_host}…")
    schedule = opendental.get_today_schedule()
    cancellations = opendental.get_today_cancellations()
    open_slots = opendental.get_open_slots()

    print(f"  {len(schedule)} appointments, {len(cancellations)} cancellations, {len(open_slots)} open slot groups")

    plain_text, blocks = messages.build_morning_message_v2(schedule, cancellations, open_slots)

    print(f"Sending to channel {channel}…")
    slack_client.send_message(channel, plain_text, blocks)
    print("Done.")


if __name__ == "__main__":
    main()
```

**Step 3: Update scripts/send_summary.py to use live data**

Replace `scripts/send_summary.py` with:

```python
#!/usr/bin/env python3
"""Manual one-shot: send daily summary now."""

import os
import sys
from datetime import date
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / ".env")

from maoffice import ai_summary, opendental, messages, slack_client


def main():
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not channel:
        print("ERROR: SLACK_CHANNEL_ID not set", file=sys.stderr)
        sys.exit(1)

    od_host = os.environ.get("OD_MYSQL_HOST")
    if not od_host:
        print("ERROR: OD_MYSQL_HOST not set", file=sys.stderr)
        sys.exit(1)

    print(f"Querying OpenDental at {od_host}…")
    production = opendental.get_daily_production()
    collections = opendental.get_collections()
    aging = opendental.get_aging_report()
    claims = opendental.get_insurance_claims_summary()
    cancellations = opendental.get_today_cancellations()

    print(f"  Production: ${production['production']:,.0f}, Procedures: {production['procedure_count']}")

    raw_text = (
        f"Date: {date.today().isoformat()}. "
        f"Procedures: {production['procedure_count']}, "
        f"Production: ${production['production']:,.0f}, "
        f"Collections: ${float(collections['patient_payments']) + float(collections['insurance_payments']):,.0f}. "
        f"Cancellations: {len(cancellations)}. "
        f"Pending claims: {claims['pending_count']}."
    )

    print("Requesting AI summary…")
    try:
        summary_text = ai_summary.summarize(raw_text)
    except Exception as e:
        print(f"AI summary failed ({e}), using raw text")
        summary_text = raw_text

    plain_text, blocks = messages.build_summary_message_v2(
        summary_text, production, collections, aging, claims, cancellations
    )

    print(f"Sending to channel {channel}…")
    slack_client.send_message(channel, plain_text, blocks)
    print("Done.")


if __name__ == "__main__":
    main()
```

**Step 4: Test syntax of both scripts**

```bash
~/pyenvs/maoffice/bin/python -c "import ast; ast.parse(open('scripts/send_morning.py').read()); print('send_morning OK')"
~/pyenvs/maoffice/bin/python -c "import ast; ast.parse(open('scripts/send_summary.py').read()); print('send_summary OK')"
```

Expected: Both print OK.

**Step 5: Commit**

```bash
git add scripts/setup_od_user.sql scripts/send_morning.py scripts/send_summary.py
git commit -m "feat: update scripts to use live OD data; add setup_od_user.sql"
```

---

## Task 13: Run full test suite + restart service

**Step 1: Run all tests**

```bash
cd ~/git/maoffice
~/pyenvs/maoffice/bin/python -m pytest tests/ -v
```

Expected: All PASSED.

**Step 2: Restart systemd service**

```bash
systemctl --user restart maoffice
systemctl --user status maoffice
```

Expected: `Active: active (running)` with no errors in the log.

**Step 3: Check logs for startup messages**

```bash
journalctl --user -u maoffice -n 30
```

Expected: Lines showing scheduler started and Slack bot thread started (or warning about missing SLACK_APP_TOKEN if not yet configured).

**Step 4: Test send_morning manually**

```bash
cd ~/git/maoffice
~/pyenvs/maoffice/bin/python scripts/send_morning.py
```

Expected: Prints appointment count, "Done." — and Slack receives the morning message.

---

## Task 14: Configure Slack app for Socket Mode + slash command (manual step)

This task is done in the Slack web UI at https://api.slack.com/apps — not in code.

**Step 1: Enable Socket Mode**
- Go to your app → Settings → Socket Mode → Enable Socket Mode
- Generate an App-Level Token with `connections:write` scope — this is your `SLACK_APP_TOKEN` (`xapp-...`)
- Add it to `.env` as `SLACK_APP_TOKEN=xapp-...`

**Step 2: Create the /od slash command**
- Go to your app → Features → Slash Commands → Create New Command
- Command: `/od`
- Request URL: (anything — Socket Mode ignores this, put `https://example.com`)
- Short Description: `Query OpenDental schedule, patients, reports`
- Save

**Step 3: Add required scopes**
- Go to OAuth & Permissions → Bot Token Scopes
- Ensure these are present: `chat:write`, `commands`
- Reinstall app to workspace if scopes changed

**Step 4: Restart daemon to pick up new token**

```bash
systemctl --user restart maoffice
journalctl --user -u maoffice -n 20
```

Expected: Log line: `Starting Slack Bolt Socket Mode handler…`

**Step 5: Test the slash command**
- In Slack, type `/od help` in the Prime Dental Care channel
- Expected: Bot responds with the help text listing all commands
- Test `/od schedule` — should return today's real appointments

---

## Done ✅

All placeholder data is replaced with live OpenDental queries. The daemon sends:
- **Morning:** Real schedule + cancellations + next-7-days open slots
- **Evening:** Production, collections, AR aging, claims, AI narrative

Staff can query on-demand via `/od` slash commands in Slack.
