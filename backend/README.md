# Notice Board Poster to Calendar Entry (P07)

A student-project MVP that turns a notice-board poster or PDF into a reviewable calendar event. It uses Azure AI Document Intelligence for OCR, Python/FastAPI for the backend, rule-based extraction (no generative model required), and standard iCalendar export.

## Features

- Upload JPG, PNG, BMP, TIFF, or PDF files (10 MB maximum).
- Extract text using Azure Document Intelligence `prebuilt-read`.
- Suggest event title, date, start/end time, and venue using transparent rules.
- Review/edit extracted details in the browser.
- Download a standard `.ics` calendar file that can be imported into Google Calendar, Outlook, Apple Calendar, and many other calendar apps.
- Interactive API documentation at `/docs` and health check at `/health`.

> Extraction is a suggestion, not a guarantee. OCR can misread posters and rule-based parsing can miss unusual date formats. Always review the event before exporting it.

## Architecture

```text
Poster / PDF
    |
    v
Browser upload UI (/app)
    |
    v
FastAPI POST /api/process
    |
    v
Azure Document Intelligence - prebuilt-read
    |
    v
OCR text + rule-based event field suggestions
    |
    v
User reviews and edits fields
    |
    v
POST /api/calendar
    |
    v
Download .ics calendar event
```

## Run locally (Windows PowerShell)

1. Install Python 3.11 or newer.
2. Open a terminal in the repository, then:

```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

3. In Azure Portal, open the **Document Intelligence** resource (not the Foundry project) → **Keys and Endpoint**. Paste its endpoint and a newly regenerated key into `.env`.
4. Start the app:

```powershell
uvicorn app.main:app --reload
```

5. Open:
   - Frontend: http://127.0.0.1:8000/app/
   - API docs: http://127.0.0.1:8000/docs
   - Health: http://127.0.0.1:8000/health

If PowerShell blocks virtual-environment activation, use `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`.

## API

### `POST /api/process`
Multipart form upload with field name `file`. Returns OCR text and suggested event fields.

### `POST /api/calendar`
JSON body:

```json
{
  "title": "AI Workshop",
  "event_date": "2026-12-05",
  "start_time": "10:00",
  "end_time": "13:00",
  "venue": "Seminar Hall",
  "description": "Workshop details"
}
```

Returns an `.ics` file. Times use 24-hour `HH:MM`; omit both times for an all-day event.

## Azure security

- Never commit `.env`, API keys, or credentials.
- The keys visible in the earlier shared screenshot must be considered exposed. Regenerate the Document Intelligence keys and the Foundry key before use.
- Use the Document Intelligence endpoint/key for OCR. The Foundry project endpoint/key is a separate service and is not used by this MVP.
- Before public deployment, set `CORS_ORIGINS` to the exact frontend origin and add authentication/rate limiting if the API is exposed publicly.

## Deployment

A Render Blueprint is provided in `render.yaml`. Create a new Web Service from this repository and set the three Azure environment variables in the Render dashboard. Do not put secret values in the YAML file.

## Project scope and limitations

- This version intentionally does not call Azure OpenAI/Foundry models; it avoids the region/deployment issue encountered during setup.
- Event extraction is rule-based and should be reviewed by the user.
- Calendar export is a downloadable `.ics` file; direct Google/Outlook account integration is not included because it requires OAuth consent and additional secrets.
- Uploaded files are processed in memory and are not stored by this application.
