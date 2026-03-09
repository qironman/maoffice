#!/usr/bin/env python3
"""Manual script: send the morning todo list to Slack right now.

Usage:
    ~/venvs/maoffice/bin/python scripts/send_morning.py
"""

import sys
import os
from pathlib import Path

# Repo root is one level up from scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

# Load .env from the repo root explicitly (works regardless of CWD)
env_file = REPO_ROOT / ".env"
if not env_file.exists():
    print(f"ERROR: {env_file} not found.")
    print(f"  Copy .env.example → .env and fill in SLACK_BOT_TOKEN and SLACK_CHANNEL_ID.")
    sys.exit(1)

load_dotenv(env_file)

# Validate required vars before doing anything
for var in ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID"):
    if not os.environ.get(var):
        print(f"ERROR: {var} is not set in {env_file}")
        sys.exit(1)

from maoffice import messages, slack_client

if __name__ == "__main__":
    from maoffice.scheduler import PLACEHOLDER_TODOS
    print("Sending morning todo list to Slack…")
    channel = os.environ["SLACK_CHANNEL_ID"]
    plain_text, blocks = messages.build_morning_message(PLACEHOLDER_TODOS)
    slack_client.send_message(channel, plain_text, blocks)
    print("Done. Check your Slack channel.")
