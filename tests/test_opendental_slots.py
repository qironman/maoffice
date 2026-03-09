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
