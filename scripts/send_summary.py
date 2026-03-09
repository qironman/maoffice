#!/usr/bin/env python3
"""Manual one-shot: send daily summary now."""

import os
import sys
from datetime import date
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / ".env")

from maoffice import ai_summary, opendental, messages, slack_client


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
    production = opendental.get_daily_production()
    collections = opendental.get_collections()
    aging = opendental.get_aging_report()
    claims = opendental.get_insurance_claims_summary()
    cancellations = opendental.get_today_cancellations()

    print(f"  Production: ${production['production']:,.0f}, Procedures: {production['procedure_count']}")

    raw_text = (
        f"Date: {date.today().isoformat()}. "
        f"Procedures: {production['procedure_count']}, "
        f"Production: ${production['production']:,.0f}, "
        f"Collections: ${float(collections['patient_payments']) + float(collections['insurance_payments']):,.0f}. "
        f"Cancellations: {len(cancellations)}. "
        f"Pending claims: {claims['pending_count']}."
    )

    print("Requesting AI summary…")
    try:
        summary_text = ai_summary.summarize(raw_text)
    except Exception as e:
        print(f"AI summary failed ({e}), using raw text")
        summary_text = raw_text

    plain_text, blocks = messages.build_summary_message_v2(
        summary_text, production, collections, aging, claims, cancellations
    )

    print(f"Sending to channel {channel}…")
    slack_client.send_message(channel, plain_text, blocks)
    print("Done.")


if __name__ == "__main__":
    main()
