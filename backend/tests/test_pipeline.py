from datetime import date

from app.main import extract_event_fields, make_ics
from app.main import CalendarEvent


def test_extracts_date_time_and_venue():
    text = "AI Workshop\nDate: 25/12/2026\nTime: 10:00 AM to 1:00 PM\nVenue: Seminar Hall"
    result = extract_event_fields(text)
    assert result["event_date"] == "2026-12-25"
    assert result["start_time"] == "10:00"
    assert result["end_time"] == "13:00"
    assert "Seminar Hall" in result["venue"]


def test_ics_contains_calendar_event():
    event = CalendarEvent(
        title="AI Workshop",
        event_date=date(2026, 12, 25),
        start_time="10:00",
        end_time="13:00",
        venue="Seminar Hall",
        description="College workshop",
    )
    output = make_ics(event)
    assert "BEGIN:VCALENDAR" in output
    assert "SUMMARY:AI Workshop" in output
    assert "DTSTART:20261225T100000" in output
    assert "END:VCALENDAR" in output



def test_extracts_registration_deadline_without_confusing_event_date():
    text = (
        "AI Workshop\\n"
        "Event Date: 25/12/2026\\n"
        "Registration deadline: 20/12/2026\\n"
        "Time: 10:00 AM to 1:00 PM\\n"
        "Venue: Seminar Hall"
    )
    result = extract_event_fields(text)
    assert result["event_date"] == "2026-12-25"
    assert result["registration_deadline"] == "2026-12-20"
    assert result["missing_fields"] == []
    assert result["requires_confirmation"] is True


def test_missing_venue_and_registration_deadline_are_reported():
    result = extract_event_fields("AI Workshop\\nDate: 25/12/2026\\nTime: 10:00 AM")
    assert "venue" in result["missing_fields"]
    assert "registration_deadline" in result["missing_fields"]
    assert result["needs_review"] is True


def test_ics_includes_registration_deadline():
    event = CalendarEvent(
        title="AI Workshop",
        event_date=date(2026, 12, 25),
        registration_deadline=date(2026, 12, 20),
    )
    output = make_ics(event)
    assert "Registration deadline: 2026-12-20" in output
