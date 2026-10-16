"""
Point d'entrée de l'application.
Lancer avec :  uvicorn main:app --port 8010 --reload
"""
import threading

from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_indexes, ping
from app.migration import migrer
from app.rag import prechauffer
from app.ocr import verifier_ocr
from app.rules_engine import init_rules
from app.routers import auth, messages, predictions, reclamations, stats, assistant, connaissances, marche

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
app.include_router(connaissances.router)
app.include_router(marche.router)


_TRADUCTIONS = {"Field required": "champ obligatoire", "Input should be a valid number": "nombre invalide",
                "Input should be a valid string": "texte invalide"}


@app.exception_handler(RequestValidationError)
async def _erreur_422(request, exc):
    """Journalise le champ refusé dans la console de l'API ET renvoie un message lisible (texte, pas
    un objet : un ancien client JavaScript afficherait sinon « [object Object] »)."""
    erreurs = exc.errors()
    details = "; ".join(f"{'.'.join(str(x) for x in e['loc'])} → {e['msg']}" for e in erreurs)
    print(f"[422] {request.method} {request.url.path} : {details}")

    if request.url.path.endswith("/documents") and any(e["loc"][-1] == "cle" and e["type"] == "missing" for e in erreurs):
        message = ("Le code de suivi n'a pas été envoyé : votre navigateur utilise une ANCIENNE version du portail. "
                   "Fermez cet onglet, rouvrez le portail et appuyez sur Ctrl+F5.")
    else:
        message = " · ".join(
            (" : ".join(filter(None, [".".join(str(x) for x in e["loc"] if x not in ("body", "query")),
                                      _TRADUCTIONS.get(e["msg"], e["msg"].replace("Value error, ", ""))])))
            for e in erreurs)
    return JSONResponse(status_code=422, content={"detail": message, "errors": jsonable_encoder(erreurs)})


@app.on_event("startup")
def on_startup():
    init_indexes()
    init_rules()
    if settings.RAG_PRECHAUFFER:
        threading.Thread(target=prechauffer, daemon=True).start()  # sans bloquer le démarrage
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
