"""APScheduler-based scheduler for morning and evening Slack notifications."""

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from maoffice import ai_summary, messages, slack_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Placeholder data (Phase 1) – replace with real OpenDental queries later
# ---------------------------------------------------------------------------

PLACEHOLDER_TODOS = [
    "Review today's appointment schedule",
    "Follow up on yesterday's outstanding claims",
    "Check lab cases due this week",
    "Morning huddle at 8:30 AM",
    "Order supplies: gloves (size M), bibs",
]

PLACEHOLDER_STATS = {
    "Patients seen": "12",
    "New patients": "2",
    "Production": "$4,200",
    "Collections": "$3,800",
    "Cancelled / No-show": "1",
}

PLACEHOLDER_RAW_DATA = (
    "Today the practice saw 12 patients including 2 new patients. "
    "Total production was $4,200 and collections were $3,800. "
    "One patient cancelled their cleaning appointment at the last minute. "
    "Dr. Smith completed 3 crowns and 5 fillings. "
    "Two patients were referred to the endodontist for root canals. "
    "Lab cases for Smith and Johnson are due Thursday. "
    "Outstanding insurance claims: 4 claims totaling $1,600 sent last week."
)


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------


def send_morning_message() -> None:
    """Build and send the morning todo list to Slack."""
    channel = os.environ["SLACK_CHANNEL_ID"]
    try:
        plain_text, blocks = messages.build_morning_message(PLACEHOLDER_TODOS)
        slack_client.send_message(channel, plain_text, blocks)
        logger.info("Morning message sent to %s", channel)
    except Exception:
        logger.exception("Failed to send morning message")


def send_daily_summary() -> None:
    """Build AI summary and send end-of-day message to Slack."""
    channel = os.environ["SLACK_CHANNEL_ID"]
    try:
        logger.info("Requesting AI summary…")
        summary_text = ai_summary.summarize(PLACEHOLDER_RAW_DATA)
    except Exception:
        logger.exception("AI summary failed; using fallback text")
        summary_text = PLACEHOLDER_RAW_DATA  # fallback: send raw data

    try:
        plain_text, blocks = messages.build_summary_message(summary_text, PLACEHOLDER_STATS)
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
        name="Morning todo list",
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
        "Scheduled morning todo at %02d:%02d and daily summary at %02d:%02d (%s)",
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
