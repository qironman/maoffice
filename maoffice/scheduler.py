"""APScheduler-based scheduler for morning and evening Slack notifications."""

import logging
import os
from datetime import date

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from maoffice import ai_summary, messages, opendental, slack_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------


def send_morning_message() -> None:
    """Fetch live OpenDental data and send morning schedule to Slack."""
    channel = os.environ["SLACK_CHANNEL_ID"]
    try:
        schedule = opendental.get_today_schedule()
        cancellations = opendental.get_today_cancellations()
        open_slots = opendental.get_open_slots()
    except Exception:
        logger.exception("Failed to query OpenDental — sending warning to Slack")
        slack_client.send_message(
            channel,
            "⚠️ maoffice: Could not reach OpenDental DB for morning report. Please check the connection.",
        )
        return

    try:
        plain_text, blocks = messages.build_morning_message_v2(schedule, cancellations, open_slots)
        slack_client.send_message(channel, plain_text, blocks)
        logger.info("Morning message sent to %s (%d appointments)", channel, len(schedule))
    except Exception:
        logger.exception("Failed to send morning message")


def send_daily_summary() -> None:
    """Fetch live OpenDental data, generate AI summary, send to Slack."""
    channel = os.environ["SLACK_CHANNEL_ID"]

    # Query OpenDental
    try:
        production = opendental.get_daily_production()
        collections = opendental.get_collections()
        claims = opendental.get_insurance_claims_summary()
        cancellations = opendental.get_today_cancellations()

        # AR aging: only on Mondays (or always — configurable via env)
        if date.today().weekday() == 0 or os.environ.get("AGING_DAILY", "").lower() == "true":
            aging = opendental.get_aging_report()
        else:
            aging = {"bal_0_30": 0.0, "bal_31_60": 0.0, "bal_61_90": 0.0,
                     "bal_91_120": 0.0, "bal_over_120": 0.0}

    except Exception:
        logger.exception("Failed to query OpenDental — sending warning to Slack")
        slack_client.send_message(
            channel,
            "⚠️ maoffice: Could not reach OpenDental DB for daily summary. Please check the connection.",
        )
        return

    # Build raw text for AI summarization
    raw_text = (
        f"Date: {date.today().isoformat()}. "
        f"Procedures completed: {production['procedure_count']}, "
        f"Production: ${production['production']:,.0f}, "
        f"Patient payments: ${collections['patient_payments']:,.0f}, "
        f"Insurance payments: ${collections['insurance_payments']:,.0f}. "
        f"Cancellations/no-shows: {len(cancellations)}. "
        f"Pending insurance claims: {claims['pending_count']} totaling ${claims['pending_total']:,.0f}. "
        f"AR over 90 days: ${float(aging.get('bal_91_120', 0)) + float(aging.get('bal_over_120', 0)):,.0f}."
    )

    try:
        ai_text = ai_summary.summarize(raw_text)
    except Exception:
        logger.exception("AI summary failed; using raw text")
        ai_text = raw_text

    try:
        plain_text, blocks = messages.build_summary_message_v2(
            ai_text, production, collections, aging, claims, cancellations
        )
        slack_client.send_message(channel, plain_text, blocks)
        logger.info("Daily summary sent to %s", channel)
    except Exception:
        logger.exception("Failed to send daily summary")


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------


def _parse_time(env_var: str, default: str) -> tuple[int, int]:
    """Parse 'HH:MM' from an env var."""
    value = os.environ.get(env_var, default)
    try:
        h, m = value.split(":")
        return int(h), int(m)
    except ValueError:
        logger.warning("Invalid time format for %s='%s'; using default %s", env_var, value, default)
        h, m = default.split(":")
        return int(h), int(m)


def create_scheduler() -> BlockingScheduler:
    """Create and configure the BlockingScheduler with morning + evening jobs."""
    timezone = os.environ.get("TIMEZONE", "America/Los_Angeles")

    morning_h, morning_m = _parse_time("MORNING_TODO_TIME", "08:00")
    summary_h, summary_m = _parse_time("DAILY_SUMMARY_TIME", "18:00")

    scheduler = BlockingScheduler(timezone=timezone)

    scheduler.add_job(
        send_morning_message,
        trigger=CronTrigger(hour=morning_h, minute=morning_m, timezone=timezone),
        id="morning_todo",
        name="Morning schedule",
        replace_existing=True,
    )

    scheduler.add_job(
        send_daily_summary,
        trigger=CronTrigger(hour=summary_h, minute=summary_m, timezone=timezone),
        id="daily_summary",
        name="Daily summary",
        replace_existing=True,
    )

    logger.info(
        "Scheduled morning at %02d:%02d and summary at %02d:%02d (%s)",
        morning_h, morning_m, summary_h, summary_m, timezone,
    )

    return scheduler


def run() -> None:
    """Start the blocking scheduler (runs forever)."""
    scheduler = create_scheduler()
    logger.info("Starting maoffice scheduler…")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
