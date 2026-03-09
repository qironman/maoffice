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
