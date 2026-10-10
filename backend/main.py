"""
Point d'entrée de l'application.
Lancer avec :  uvicorn main:app --port 8010 --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_indexes, ping
from app.migration import migrer
from app.ocr import verifier_ocr
from app.rules_engine import init_rules
from app.routers import auth, messages, predictions, reclamations, stats, assistant

app = FastAPI(
    title="GEIF — Traitement Automatique des Réclamations (IS, IR, TVA)",
    version="2.1.0",
    description="Backend : FastAPI + MongoDB + génération par LLM (Groq) + apprentissage bayésien.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(reclamations.router)
app.include_router(stats.router)
app.include_router(predictions.router)
app.include_router(messages.router)
app.include_router(assistant.router)


@app.on_event("startup")
def on_startup():
    init_indexes()
    init_rules()
    bilan = migrer()  # idempotent : anciens rôles/statuts -> nouveaux
    if any(bilan.values()):
        print(f"[MIGRATION] {bilan}")


@app.get("/health")
def health():
    return {
        "ok": True,
        "groq_configure": bool(settings.GROQ_API_KEY),
        "mongo_connecte": ping(),
        "email": {
            "ok": settings.email_configure(),
            "message": "SMTP configuré." if settings.email_configure()
            else "SMTP non configuré — remplis SMTP_HOST/SMTP_USER/SMTP_PASSWORD dans backend/.env (voir .env.example).",
        },
        "ocr": verifier_ocr(),
    }
