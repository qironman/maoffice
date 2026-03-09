#!/usr/bin/env python3
"""Manual one-shot: send morning schedule message now."""

import os
import sys
from pathlib import Path

# Load .env from repo root
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / ".env")

from maoffice import opendental, messages, slack_client


def main():
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not channel:
        print("ERROR: SLACK_CHANNEL_ID not set", file=sys.stderr)
        sys.exit(1)

    od_host = os.environ.get("OD_MYSQL_HOST")
    if not od_host:
        print("ERROR: OD_MYSQL_HOST not set", file=sys.stderr)
        sys.exit(1)

    print(f"Querying OpenDental at {od_host}…")
    schedule = opendental.get_today_schedule()
    cancellations = opendental.get_today_cancellations()
    open_slots = opendental.get_open_slots()

    print(f"  {len(schedule)} appointments, {len(cancellations)} cancellations, {len(open_slots)} open slot groups")

    plain_text, blocks = messages.build_morning_message_v2(schedule, cancellations, open_slots)

    print(f"Sending to channel {channel}…")
    slack_client.send_message(channel, plain_text, blocks)
    print("Done.")


if __name__ == "__main__":
    main()
