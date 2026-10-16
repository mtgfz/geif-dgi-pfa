# GEIF — API (FastAPI + Tesseract + RAG). Contexte de construction : la RACINE du dépôt (voir docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    TOKENIZERS_PARALLELISM=false

# Tesseract avec le français et l'arabe (les .traineddata sont inclus : plus aucun réglage de langue à faire)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch version CPU d'abord : l'image est ~1 Go plus légère que la version GPU, inutile ici
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Modèle de recherche du RAG téléchargé UNE fois à la construction : le démarrage ne dépend plus d'Internet
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Code et données nécessaires à l'exécution (voir .dockerignore pour ce qui est exclu)
COPY backend backend
COPY rag rag
COPY market_data/scraper/ammc_filings.csv market_data/scraper/parsed_financials.csv market_data/scraper/
COPY time_series time_series
COPY data/generators/generate_fiscal_timeseries.py data/generators/

# Utilisateur non privilégié ; .cache = séries simulées des prévisions
RUN useradd --create-home geif && mkdir -p /app/backend/.cache && chown -R geif /app/backend/.cache /app/rag
USER geif

WORKDIR /app/backend
EXPOSE 8010
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=8 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/health', timeout=4)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
