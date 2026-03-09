"""Slack Bolt Socket Mode app for /od slash commands.

Runs as a thread alongside the APScheduler daemon.
Requires SLACK_APP_TOKEN (xapp-...) and SLACK_BOT_TOKEN in environment.
"""

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "*/od* commands:\n"
    "• `/od schedule` — Today's appointments\n"
    "• `/od patient <name>` — Look up a patient\n"
    "• `/od aging` — AR aging report\n"
    "• `/od production` — Today's production + collections\n"
    "• `/od openslots` — Open slots this week\n"
    "• `/od help` — This help message"
)


# ---------------------------------------------------------------------------
# Command parsing (pure functions — easy to test)
# ---------------------------------------------------------------------------


def parse_od_command(text: str) -> tuple[str, str]:
    """Parse '/od <subcommand> [args]' text.

    Returns (subcommand, args_string).
    """
    text = text.strip()
    if not text:
        return ("help", "")
    parts = text.split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    valid = {"schedule", "patient", "aging", "production", "openslots", "help"}
    if cmd not in valid:
        return ("unknown", text)
    return (cmd, args)


# ---------------------------------------------------------------------------
# Response formatters (pure functions — easy to test)
# ---------------------------------------------------------------------------


def format_schedule_response(schedule: list[dict], cancellations: list[dict]) -> str:
    if not schedule:
        lines = ["No appointments scheduled today."]
    else:
        lines = [f"*Today's Schedule ({len(schedule)} appointments):*"]
        for a in schedule:
            t = str(a.get("AptDateTime", ""))
            time_str = t[11:16] if len(t) >= 16 else t
            lines.append(
                f"• {time_str}  {a.get('PatientName', '')}  [{a.get('ProvAbbr', '')}]  {a.get('ProcDescript', '')}"
            )
    if cancellations:
        lines.append(f"\n*Cancellations ({len(cancellations)}):*")
        for c in cancellations:
            lines.append(f"• {c.get('PatientName', '')}  {c.get('ProcDescript', '')}")
    return "\n".join(lines)


def format_patient_response(patients: list[dict], search: str) -> str:
    if not patients:
        return f"No patients found matching _{search}_."
    lines = [f"*Patients matching '{search}':*"]
    for p in patients:
        next_apt = p.get("NextAptDate") or "none scheduled"
        lines.append(
            f"• *{p.get('LName')}, {p.get('FName')}*  "
            f"DOB: {str(p.get('Birthdate', ''))[:10]}  "
            f"Balance: ${float(p.get('BalTotal', 0)):,.0f}  "
            f"Insurance: {p.get('PriCarrier', 'none')}  "
            f"Next appt: {str(next_apt)[:16]}"
        )
    return "\n".join(lines)


def format_aging_response(aging: dict) -> str:
    total = sum(float(v) for v in aging.values())
    return (
        f"*AR Aging Report:*\n"
        f"• 0-30 days:   ${float(aging.get('bal_0_30', 0)):,.0f}\n"
        f"• 31-60 days:  ${float(aging.get('bal_31_60', 0)):,.0f}\n"
        f"• 61-90 days:  ${float(aging.get('bal_61_90', 0)):,.0f}\n"
        f"• 91-120 days: ${float(aging.get('bal_91_120', 0)):,.0f}\n"
        f"• 120+ days:   ${float(aging.get('bal_over_120', 0)):,.0f}\n"
        f"• *Total outstanding: ${total:,.0f}*"
    )


def format_production_response(production: dict, collections: dict) -> str:
    total_collect = float(collections.get("patient_payments", 0)) + float(collections.get("insurance_payments", 0))
    return (
        f"*Today's Production & Collections:*\n"
        f"• Production: ${float(production.get('production', 0)):,.0f} "
        f"({production.get('procedure_count', 0)} procedures)\n"
        f"• Collections: ${total_collect:,.0f} "
        f"(patient: ${float(collections.get('patient_payments', 0)):,.0f} | "
        f"insurance: ${float(collections.get('insurance_payments', 0)):,.0f})"
    )


def format_openslots_response(slots: list[dict]) -> str:
    if not slots:
        return "No open slots found in the next 7 days — schedule is full! 🎉"
    lines = ["*Open Slots — Next 7 Days:*"]
    for s in slots:
        lines.append(f"• {s.get('SchedDate', '')}  [{s.get('ProvAbbr', '')}]  {s.get('OpenSlots', 0)} slot(s)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bolt app (only imported when SLACK_APP_TOKEN is available)
# ---------------------------------------------------------------------------


def build_app():
    """Build and return the Slack Bolt App instance."""
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    from maoffice import opendental

    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    allowed_channel = os.environ.get("SLACK_CHANNEL_ID", "")

    @app.command("/od")
    def handle_od(ack, respond, command):
        ack()  # Must acknowledge within 3 seconds
        if allowed_channel and command.get("channel_id") != allowed_channel:
            respond("⚠️ This command is only available in the designated channel.")
            return
        text = command.get("text", "")
        cmd, args = parse_od_command(text)

        try:
            if cmd == "help" or cmd == "unknown":
                respond(HELP_TEXT)

            elif cmd == "schedule":
                schedule = opendental.get_today_schedule()
                cancellations = opendental.get_today_cancellations()
                respond(format_schedule_response(schedule, cancellations))

            elif cmd == "patient":
                if not args:
                    respond("Usage: `/od patient <last name>`")
                    return
                patients = opendental.find_patients(args)
                respond(format_patient_response(patients, args))

            elif cmd == "aging":
                aging = opendental.get_aging_report()
                respond(format_aging_response(aging))

            elif cmd == "production":
                production = opendental.get_daily_production()
                collections = opendental.get_collections()
                respond(format_production_response(production, collections))

            elif cmd == "openslots":
                slots = opendental.get_open_slots()
                respond(format_openslots_response(slots))

        except Exception as e:
            logger.exception("Error handling /od %s", cmd)
            respond(f"⚠️ Error: could not complete request. ({type(e).__name__}: {e})")

    return app


def start_in_thread() -> threading.Thread:
    """Start the Slack Bolt Socket Mode handler in a daemon thread.

    Returns the thread (already started).
    Logs a warning and returns immediately if SLACK_APP_TOKEN is not set.
    """
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        logger.warning("SLACK_APP_TOKEN not set — Slack bot slash commands disabled")
        # Return a dummy thread that does nothing
        t = threading.Thread(target=lambda: None, daemon=True)
        t.start()
        return t

    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = build_app()
    handler = SocketModeHandler(app, app_token)

    def _run():
        logger.info("Starting Slack Bolt Socket Mode handler…")
        handler.start()

    t = threading.Thread(target=_run, daemon=True, name="slack-bolt")
    t.start()
    return t
