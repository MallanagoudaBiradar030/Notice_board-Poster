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
