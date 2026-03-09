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
