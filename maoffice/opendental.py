"""OpenDental MySQL query layer.

All functions open a fresh connection, run the query, close the connection.
No persistent pool — queries are low-frequency (a few times per day).
"""

import os
from datetime import date, timedelta
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
    today = date.today().strftime("%Y-%m-%d")
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
    today = date.today().strftime("%Y-%m-%d")
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


def get_open_slots(days_ahead: int = 7) -> list[dict[str, Any]]:
    """Return working days in the next N days with scheduled hours and appointment counts.

    Uses SchedType=1 (provider working blocks) to find days the office is open,
    then counts booked appointments per provider per day. Hygiene appointments
    are booked under the primary provider (ProvNum) but assigned to the hygienist
    via ProvHyg — both fields are checked so hygienists show correct counts.

    Returns list of dicts: {SchedDate, ProvAbbr, WorkHours, AptCount}
    """
    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    sql = """
        SELECT
            s.SchedDate,
            pr.Abbr AS ProvAbbr,
            ROUND(SUM(TIME_TO_SEC(TIMEDIFF(s.StopTime, s.StartTime))) / 3600, 1) AS WorkHours,
            COALESCE((
                SELECT COUNT(*) FROM appointment a
                WHERE (a.ProvNum = s.ProvNum OR a.ProvHyg = s.ProvNum)
                  AND DATE(a.AptDateTime) = s.SchedDate
                  AND a.AptStatus NOT IN (2, 5)
            ), 0) AS AptCount
        FROM schedule s
        JOIN provider pr ON pr.ProvNum = s.ProvNum
        WHERE s.SchedDate >= %s
          AND s.SchedDate < %s
          AND s.SchedType = 1
        GROUP BY s.SchedDate, s.ProvNum
        ORDER BY s.SchedDate, pr.Abbr
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (today.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
            return cur.fetchall()


def get_daily_production() -> dict[str, Any]:
    """Return today's production: total fee and procedure count.

    Returns dict: {production: float, procedure_count: int}
    """
    today = date.today().strftime("%Y-%m-%d")
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
    today = date.today().strftime("%Y-%m-%d")

    patient_sql ="""
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


def get_aging_report() -> dict[str, Any]:
    """Return AR aging buckets across all patients with outstanding balances.

    OpenDental stores pre-computed aging in the patient table.
    This instance uses 4 buckets: 0-30, 31-60, 61-90, 90+.
    Returns dict: {bal_0_30, bal_31_60, bal_61_90, bal_over_90} all as floats.
    """
    sql = """
        SELECT
            COALESCE(SUM(Bal_0_30), 0)  AS bal_0_30,
            COALESCE(SUM(Bal_31_60), 0) AS bal_31_60,
            COALESCE(SUM(Bal_61_90), 0) AS bal_61_90,
            COALESCE(SUM(BalOver90), 0) AS bal_over_90
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
                "bal_over_90": 0.0,
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
    """Search patients by name (case-insensitive, partial match).

    Handles single token (searches LName and FName), or two tokens separated by
    a space or comma (tries "First Last" and "Last First" orderings).

    Returns list of dicts with keys:
        PatNum, LName, FName, Birthdate, BalTotal, NextAptDate, PriCarrier
    """
    base_select = """
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
        LEFT JOIN patplan pp ON pp.PatNum = p.PatNum AND pp.Ordinal = 1
        LEFT JOIN inssub isub ON isub.InsSubNum = pp.InsSubNum
        LEFT JOIN insplan ip ON ip.PlanNum = isub.PlanNum
        LEFT JOIN carrier ic ON ic.CarrierNum = ip.CarrierNum
        WHERE p.PatStatus = 0
    """

    # Normalise: strip commas so "Tian, Ye" and "Tian Ye" are treated the same
    tokens = search.replace(",", " ").split()

    if len(tokens) >= 2:
        # Two tokens: try (LName=token[0], FName=token[1]) OR (LName=token[1], FName=token[0])
        a, b = tokens[0], tokens[1]
        sql = base_select + """
          AND (
            (p.LName LIKE %s AND p.FName LIKE %s)
            OR
            (p.LName LIKE %s AND p.FName LIKE %s)
          )
          ORDER BY p.LName, p.FName
          LIMIT 10
        """
        params = (f"%{a}%", f"%{b}%", f"%{b}%", f"%{a}%")
    else:
        # Single token: match anywhere in LName or FName
        token = tokens[0] if tokens else search
        sql = base_select + """
          AND (p.LName LIKE %s OR p.FName LIKE %s)
          ORDER BY p.LName, p.FName
          LIMIT 10
        """
        params = (f"%{token}%", f"%{token}%")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
