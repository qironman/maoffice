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
