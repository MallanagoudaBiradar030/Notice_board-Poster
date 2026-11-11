# P07 — Notice-Board Poster to Calendar Entry

A student hackathon project that converts college notice-board posters into reviewable calendar events.

## Current MVP

- Azure AI Document Intelligence OCR for poster/PDF text extraction.
- FastAPI backend.
- Rule-based extraction suggestions for title, date, time and venue (no generative model required).
- Browser interface to upload a poster and edit the extracted event.
- Downloadable iCalendar (.ics) file for Google Calendar, Outlook and other calendar apps.
- API documentation at `/docs`, health endpoint at `/health`.

## Run locally

See [backend/README.md](backend/README.md) for the full Windows setup, Azure configuration, API details and deployment instructions.

Quick start from the repository root (Windows PowerShell):

```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your Azure Document Intelligence endpoint and newly regenerated key.
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Important

Never commit API keys. Keys visible in a previously shared screenshot must be regenerated. This is an MVP: always verify the suggested date/time/venue before importing the calendar file. Direct Google/Outlook OAuth calendar insertion is not included yet.
