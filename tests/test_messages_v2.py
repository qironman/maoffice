"""Tests for new message formatters added in Phase 2."""
from maoffice import messages


def test_build_morning_message_with_schedule():
    """build_morning_message() should include schedule and open slots sections."""
    schedule = [
        {"AptDateTime": "2026-03-09 09:00:00", "PatientName": "Doe, Jane",
         "ProvAbbr": "DR", "ProcDescript": "Cleaning"},
    ]
    cancellations = []
    open_slots = [{"SchedDate": "2026-03-10", "ProvAbbr": "DR", "OpenSlots": 2}]

    text, blocks = messages.build_morning_message_v2(schedule, cancellations, open_slots)

    assert "Doe, Jane" in text or any(
        "Doe, Jane" in str(b) for b in blocks
    )
    assert isinstance(blocks, list)
    assert len(blocks) > 0


def test_build_summary_message_with_stats():
    """build_summary_message_v2() should format production + aging."""
    production = {"production": 4200.0, "procedure_count": 15}
    collections = {"patient_payments": 1200.0, "insurance_payments": 2600.0}
    aging = {"bal_0_30": 500.0, "bal_31_60": 200.0, "bal_61_90": 100.0,
             "bal_91_120": 50.0, "bal_over_120": 25.0}
    claims = {"pending_count": 3, "pending_total": 1800.0,
              "rejected_count": 1, "rejected_total": 600.0}
    cancellations = [{"PatientName": "Smith, Bob", "ProcDescript": "Crown"}]
    ai_summary = "Great day! 15 procedures completed."

    text, blocks = messages.build_summary_message_v2(
        ai_summary, production, collections, aging, claims, cancellations
    )

    assert "$4,200" in text or "$4200" in text or "4200" in str(blocks)
    assert isinstance(blocks, list)
