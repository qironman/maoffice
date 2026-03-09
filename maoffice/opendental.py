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
