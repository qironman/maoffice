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
