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
    """Return open appointment slots for the next N days grouped by date + provider.

    OpenDental tracks available blocks in the `schedule` table. An open slot
    is a scheduled block with no appointment booked against it.
    Returns list of dicts: {SchedDate, ProvAbbr, OpenSlots}
    """
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
        LEFT JOIN patplan pp ON pp.PatNum = p.PatNum AND pp.Ordinal = 1
        LEFT JOIN inssub isub ON isub.InsSubNum = pp.InsSubNum
        LEFT JOIN insplan ip ON ip.PlanNum = isub.PlanNum
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
