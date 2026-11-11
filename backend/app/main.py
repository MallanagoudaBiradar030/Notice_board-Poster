import json
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
    description: str = Field(default="", max_length=5000)
    registration_deadline: date | None = None


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
    """Use the existing Foundry prompt agent to turn OCR text into structured event data."""
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
    agent_name = os.getenv("FOUNDRY_AGENT_NAME", "chatgpt4mini")
    api_key = os.getenv("FOUNDRY_API_KEY", "")
    if not endpoint or not api_key:
        raise HTTPException(
            status_code=503,
            detail="Microsoft Foundry is not configured. Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_API_KEY.",
        )

    today = date.today().isoformat()
    instructions = f"""Extract event details from the OCR text below.
Today's date is {today}. Return ONLY one valid JSON object with these keys:
title, event_date, start_time, end_time, venue, description, registration_deadline, needs_review, review_notes.
Use ISO dates (YYYY-MM-DD) and 24-hour times (HH:MM). Use null for any missing or ambiguous date/time/deadline.
Do not guess or invent details. Relative dates such as 'next Friday' must remain unresolved: set event_date to null and explain in review_notes.
Set needs_review=true if any important field is missing or ambiguous. registration_deadline must be null if not explicitly stated.
OCR TEXT:
{text[:12000]}"""

    url = f"{endpoint}/agents/{agent_name}/endpoint/protocols/openai/responses"
    try:
        response = requests.post(
            url,
            params={"api-version": "v1"},
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={"input": instructions, "stream": False},
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        detail = "Foundry agent request failed."
        if getattr(exc, "response", None) is not None:
            detail += f" HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        raise HTTPException(status_code=502, detail=detail) from exc

    output = payload.get("output_text", "")
    if not output:
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    output += content.get("text", "")
    try:
        clean = output.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I)
        event = json.loads(clean)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Foundry agent returned invalid JSON. Check the agent instructions and try again.") from exc

    allowed = {"title", "event_date", "start_time", "end_time", "venue", "description", "registration_deadline", "needs_review", "review_notes"}
    event = {key: event.get(key) for key in allowed}
    event.setdefault("needs_review", True)
    event.setdefault("review_notes", [])
    return event


def ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n").replace("\r", "")


def make_ics(event: CalendarEvent) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"{uuid4()}@notice-board-poster"
    summary = ics_escape(event.title)
    description = ics_escape(event.description)
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
