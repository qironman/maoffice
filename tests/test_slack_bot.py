"""Tests for slack_bot.py command parsing."""
from maoffice import slack_bot


def test_parse_od_command_schedule():
    assert slack_bot.parse_od_command("schedule") == ("schedule", "")


def test_parse_od_command_patient():
    assert slack_bot.parse_od_command("patient Jane Doe") == ("patient", "Jane Doe")


def test_parse_od_command_unknown():
    cmd, _ = slack_bot.parse_od_command("blah")
    assert cmd == "unknown"


def test_parse_od_command_empty():
    cmd, _ = slack_bot.parse_od_command("")
    assert cmd == "help"


def test_format_schedule_response_empty():
    text = slack_bot.format_schedule_response([], [])
    assert "No appointments" in text


def test_format_schedule_response_with_data():
    schedule = [
        {"AptDateTime": "2026-03-09 09:00:00", "PatientName": "Doe, Jane",
         "ProvAbbr": "DR", "ProcDescript": "Cleaning"}
    ]
    text = slack_bot.format_schedule_response(schedule, [])
    assert "Doe, Jane" in text


def test_format_patient_response_not_found():
    text = slack_bot.format_patient_response([], "Smith")
    assert "No patients found" in text


def test_format_aging_response():
    aging = {"bal_0_30": 500.0, "bal_31_60": 200.0, "bal_61_90": 100.0,
             "bal_91_120": 50.0, "bal_over_120": 25.0}
    text = slack_bot.format_aging_response(aging)
    assert "0-30" in text
    assert "$500" in text
