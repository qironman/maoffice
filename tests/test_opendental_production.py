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
