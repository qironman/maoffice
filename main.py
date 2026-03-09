#!/usr/bin/env python3
"""Entry point for the maoffice daemon.

Starts two concurrent components:
1. Slack Bolt Socket Mode thread — handles /od slash commands
2. APScheduler blocking loop — sends morning + evening Slack messages
"""

import logging
import os

from dotenv import load_dotenv

# Load .env before importing any maoffice modules (they read env vars at import time)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from maoffice import slack_bot
from maoffice.scheduler import run

if __name__ == "__main__":
    # Start Slack bot in background thread (gracefully skipped if SLACK_APP_TOKEN unset)
    slack_bot.start_in_thread()
    # Run scheduler in foreground (blocks until Ctrl+C / systemd stop)
    run()
