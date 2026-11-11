import os
import time
from typing import Any

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Notice Board Poster to Calendar API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your deployed frontend origin before production.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/bmp", "image/tiff", "application/pdf"}


def azure_read_document(content: bytes) -> dict[str, Any]:
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "").rstrip("/")
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    api_version = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30")
    if not endpoint or not key:
        raise HTTPException(status_code=503, detail="Azure Document Intelligence is not configured. Set the endpoint and key in backend/.env.")

    analyze_url = f"{endpoint}/documentintelligence/documentModels/prebuilt-read:analyze?api-version={api_version}"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/octet-stream"}
    try:
        response = requests.post(analyze_url, headers=headers, data=content, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Azure OCR request failed: {exc}") from exc

    operation_url = response.headers.get("Operation-Location")
    if not operation_url:
        raise HTTPException(status_code=502, detail="Azure did not return an Operation-Location header.")

    poll_headers = {"Ocp-Apim-Subscription-Key": key}
    for _ in range(30):
        time.sleep(2)
        try:
            poll = requests.get(operation_url, headers=poll_headers, timeout=30)
            poll.raise_for_status()
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Azure OCR polling failed: {exc}") from exc
        result = poll.json()
        status = result.get("status")
        if status == "succeeded":
            return result
        if status == "failed":
            raise HTTPException(status_code=422, detail="Azure could not read this document.")
    raise HTTPException(status_code=504, detail="Azure OCR timed out. Try the upload again.")


@app.get("/")
def root():
    return {"message": "Notice Board Poster to Calendar API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/ocr")
async def extract_notice_text(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, BMP, TIFF, or PDF file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    result = azure_read_document(content)
    analyze_result = result.get("analyzeResult", {})
    pages = analyze_result.get("pages", [])
    lines = [line.get("content", "") for page in pages for line in page.get("lines", [])]
    text = "\n".join(lines).strip()
    return {
        "filename": file.filename,
        "status": result.get("status"),
        "text": text,
        "page_count": len(pages),
        "message": "Text extracted. Event/date/time structuring and calendar export are the next stage.",
    }
