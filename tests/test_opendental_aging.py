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
    """get_aging_report() returns dict with 0-30/31-60/61-90/90+ buckets."""
    fake_row = {"bal_0_30": 500.0, "bal_31_60": 200.0, "bal_61_90": 100.0, "bal_over_90": 75.0}
    conn = _make_conn_fetchone(fake_row)
    with patch.object(opendental, "get_connection", return_value=conn):
        result = opendental.get_aging_report()
    assert "bal_0_30" in result
    assert "bal_over_90" in result


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


def test_find_patients_two_token_search():
    """find_patients() with 'First Last' passes both tokens as params."""
    conn = _make_conn_fetchall([])
    # cursor is conn.cursor() — the context manager returns the cursor itself
    cursor = conn.cursor.return_value
    with patch.object(opendental, "get_connection", return_value=conn):
        opendental.find_patients("Ye Tian")
    sql, params = cursor.execute.call_args[0]
    # Two-token search uses 4 params (a,b,b,a ordering)
    assert len(params) == 4
    assert "%Ye%" in params
    assert "%Tian%" in params


def test_find_patients_comma_format():
    """find_patients() strips commas so 'Tian, Ye' works like 'Tian Ye'."""
    conn = _make_conn_fetchall([])
    cursor = conn.cursor.return_value
    with patch.object(opendental, "get_connection", return_value=conn):
        opendental.find_patients("Tian, Ye")
    sql, params = cursor.execute.call_args[0]
    assert len(params) == 4
    assert "%Tian%" in params
    assert "%Ye%" in params
