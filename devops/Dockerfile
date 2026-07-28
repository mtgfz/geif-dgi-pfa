# GEIF — Backend API (FastAPI)
FROM python:3.11-slim

# Tesseract OCR + pack de langue française (nécessaire pour cv_ocr)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY cv_ocr/ ./cv_ocr/
COPY ml_classification/ ./ml_classification/

WORKDIR /app/backend
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
