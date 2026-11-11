# Notice Board Poster to Calendar Entry — Backend

FastAPI backend starter for the P07 project. It accepts a notice-board poster or PDF and extracts text using Azure AI Document Intelligence (`prebuilt-read`).

## 1. Setup

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the endpoint and key from your Azure Document Intelligence resource. **Never commit `.env` or paste the key into GitHub.**

## 2. Run

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`, then test `POST /api/ocr` with a JPG, PNG, BMP, TIFF, or PDF (maximum 10 MB).

## 3. Azure resource values

In Azure Portal, open your **Document Intelligence** resource → **Keys and Endpoint**. Copy the endpoint and one key into `backend/.env`.

## Current scope

- Health check: `GET /health`
- OCR upload: `POST /api/ocr`
- Azure `prebuilt-read` asynchronous operation polling

## Next implementation stages

1. Convert OCR text into structured notice fields (title, event date, start/end time, venue, description).
2. Add validation and a user confirmation/edit screen.
3. Generate an `.ics` calendar file or integrate Google Calendar / Microsoft Outlook with user authorization.
4. Configure CORS to allow only the deployed frontend origin before production.
