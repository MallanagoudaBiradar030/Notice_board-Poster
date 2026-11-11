import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from dateutil import parser as date_parser
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(
    title="Notice Board Poster to Calendar API",
    description="Extract notice text, review event details, and download a calendar event.",
    version="1.0.0",
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/bmp", "image/tiff",
    "application/pdf",
}
MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_PATTERNS = [
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    rf"\b\d{{1,2}}\s+{MONTH}\s+\d{{4}}\b",
    rf"\b{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b",
]
TIME_PATTERN = re.compile(r"\b(0?[1-9]|1[0-2])(?::([0-5]\d))?\s*(AM|PM)\b|\b([01]?\d|2[0-3]):([0-5]\d)\b", re.I)


class CalendarEvent(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    event_date: date
    start_time: str | None = None
    end_time: str | None = None
    venue: str = Field(default="", max_length=300)
    registration_deadline: date | None = None
    description: str = Field(default="", max_length=5000)


def azure_read_document(content: bytes) -> dict[str, Any]:
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "").rstrip("/")
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    api_version = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30")
    if not endpoint or not key:
        raise HTTPException(
            status_code=503,
            detail="Azure Document Intelligence is not configured. Add its endpoint and a newly regenerated key to backend/.env.",
        )

    url = f"{endpoint}/documentintelligence/documentModels/prebuilt-read:analyze?api-version={api_version}"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/octet-stream"}
    try:
        response = requests.post(url, headers=headers, data=content, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Azure OCR request failed: {exc}") from exc

    operation_url = response.headers.get("Operation-Location")
    if not operation_url:
        raise HTTPException(status_code=502, detail="Azure did not return an Operation-Location header.")

    for _ in range(45):
        time.sleep(2)
        try:
            poll = requests.get(operation_url, headers={"Ocp-Apim-Subscription-Key": key}, timeout=30)
            poll.raise_for_status()
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Azure OCR polling failed: {exc}") from exc
        result = poll.json()
        if result.get("status") == "succeeded":
            return result
        if result.get("status") == "failed":
            raise HTTPException(status_code=422, detail="Azure could not read this document.")
    raise HTTPException(status_code=504, detail="Azure OCR timed out. Try again.")


def get_ocr_text(result: dict[str, Any]) -> tuple[str, int]:
    analysis = result.get("analyzeResult", {})
    pages = analysis.get("pages", [])
    lines = [line.get("content", "") for page in pages for line in page.get("lines", [])]
    text = "\n".join(lines).strip() or analysis.get("content", "").strip()
    return text, len(pages)


def extract_event_fields(text: str) -> dict[str, Any]:
    lines = [re.sub(r"\s+", " ", line).strip(" •|:-") for line in text.splitlines()]
    lines = [line for line in lines if line]
    title = next((line for line in lines if len(line) >= 4), "")
    venue = ""
    for line in lines:
        if re.search(r"\b(venue|location|place|hall|auditorium|room)\b", line, re.I):
            venue = re.sub(r"^(venue|location|place)\s*[:\-]?\s*", "", line, flags=re.I)
            break

    deadline_line = next(
        (line for line in lines if re.search(r"\b(registration deadline|registration closes|register by|last date to register|last date for registration)\\b", line, re.I)),
        "",
    )
    registration_deadline = None
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, deadline_line, re.I)
        if match:
            try:
                registration_deadline = date_parser.parse(match.group(0), dayfirst=True, fuzzy=False).date()
                break
            except (ValueError, OverflowError):
                pass

    event_text = "\n".join(
        line for line in lines
        if not re.search(r"\b(registration deadline|registration closes|register by|last date to register|last date for registration)\\b", line, re.I)
    )
    found_date = None
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, event_text, re.I)
        if match:
            try:
                found_date = date_parser.parse(match.group(0), dayfirst=True, fuzzy=False).date()
                break
            except (ValueError, OverflowError):
                pass

    times = []
    for match in TIME_PATTERN.finditer(text):
        raw = match.group(0).upper().replace(" ", "")
        try:
            parsed = datetime.strptime(raw, "%I:%M%p") if "AM" in raw or "PM" in raw else datetime.strptime(raw, "%H:%M")
            times.append(parsed.strftime("%H:%M"))
        except ValueError:
            continue

    suggestions = {
        "title": title[:200] or None,
        "event_date": found_date.isoformat() if found_date else None,
        "start_time": times[0] if times else None,
        "venue": venue[:300] or None,
        "registration_deadline": registration_deadline.isoformat() if registration_deadline else None,
    }
    missing_fields = [field for field, value in suggestions.items() if not value]

    return {
        **suggestions,
        "end_time": times[1] if len(times) > 1 else None,
        "description": text[:5000],
        "missing_fields": missing_fields,
        "requires_confirmation": True,
        "needs_review": bool(missing_fields),
        "note": "These are OCR/rule-based suggestions, not verified facts. Review every field and fill missing or unclear details before confirming.",
    }


def ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n").replace("\r", "")


def make_ics(event: CalendarEvent) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"{uuid4()}@notice-board-poster"
    summary = ics_escape(event.title)
    deadline_note = (
        f"\nRegistration deadline: {event.registration_deadline.isoformat()}"
        if event.registration_deadline else ""
    )
    description = ics_escape(event.description + deadline_note)
    location = ics_escape(event.venue)
    if event.start_time:
        start = datetime.combine(event.event_date, datetime.strptime(event.start_time, "%H:%M").time())
        end = datetime.combine(event.event_date, datetime.strptime(event.end_time, "%H:%M").time()) if event.end_time else start + timedelta(hours=1)
        start_line = f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}"
        end_line = f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}"
    else:
        start_line = f"DTSTART;VALUE=DATE:{event.event_date.strftime('%Y%m%d')}"
        end_line = f"DTEND;VALUE=DATE:{(event.event_date + timedelta(days=1)).strftime('%Y%m%d')}"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Notice Board Poster//Calendar Entry//EN",
        "CALSCALE:GREGORIAN", "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}",
        start_line, end_line, f"SUMMARY:{summary}", f"LOCATION:{location}",
        f"DESCRIPTION:{description}", "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


@app.get("/")
def root():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/process")
async def process_notice(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, BMP, TIFF, or PDF file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")
    result = azure_read_document(content)
    text, page_count = get_ocr_text(result)
    if not text:
        raise HTTPException(status_code=422, detail="No readable text was found in this file.")
    return {
        "filename": file.filename,
        "page_count": page_count,
        "text": text,
        "event": extract_event_fields(text),
    }


@app.post("/api/calendar")
def create_calendar_file(event: CalendarEvent):
    if event.start_time:
        try:
            datetime.strptime(event.start_time, "%H:%M")
            if event.end_time:
                datetime.strptime(event.end_time, "%H:%M")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Times must use 24-hour HH:MM format, for example 14:30.") from exc
    elif event.end_time:
        raise HTTPException(status_code=422, detail="Provide a start time when providing an end time.")
    calendar = make_ics(event)
    filename = re.sub(r"[^A-Za-z0-9_-]+", "-", event.title).strip("-")[:50] or "notice-event"
    return Response(
        content=calendar,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.ics"'},
    )


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/app", StaticFiles(directory=static_dir, html=True), name="frontend")
