# P07 — Notice-Board Poster to Calendar Entry

A student hackathon project that converts college notice-board posters into reviewable calendar events.

## Current MVP

- Azure AI Document Intelligence OCR for poster/PDF text extraction.
- FastAPI backend.
- Existing Microsoft Foundry `chatgpt4mini` prompt agent converts OCR text into structured event details.
- Missing or ambiguous values are flagged for manual review; relative dates are not silently guessed.
- Editable registration deadline field.
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
# Configure Azure OCR and Foundry values in backend/.env. Never commit secrets.
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Required environment variables

- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`
- `FOUNDRY_PROJECT_ENDPOINT` (your Foundry project endpoint)
- `FOUNDRY_AGENT_NAME` (`chatgpt4mini`)
- `FOUNDRY_API_KEY` (store securely; never commit it)

## Important

Never commit API keys. Keys visible in a previously shared screenshot must be regenerated. This is an MVP: always verify the suggested date/time/venue before importing the calendar file. Direct Google/Outlook OAuth calendar insertion is not included yet.
