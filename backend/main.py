"""
GEIF - API principale
=========================
Endpoints :
  POST /documents/upload   -> traite un document (OCR -> classification -> validation -> anomalies)
  GET  /documents           -> liste des documents traités
  GET  /documents/{id}      -> détail d'un document
  GET  /stats                -> statistiques agrégées pour le dashboard

Lancer localement :
    uvicorn main:app --reload --port 8000
"""
import shutil
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

# Chemins vers les autres piliers du projet (repo mono-dépôt, plusieurs dossiers)
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "cv_ocr"))
sys.path.append(str(ROOT / "ml_classification"))

from anomaly import compute_reference_stats, flag_anomalies  # noqa: E402
from classifier import DocumentClassifier  # noqa: E402
from database import DocumentRecord, get_db, init_db  # noqa: E402
from ocr import extract_fields, extract_text  # noqa: E402

app = FastAPI(title="GEIF API", description="Gestion Electronique Intelligente des Flux fiscaux")

UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MODEL_PATH = str(ROOT / "ml_classification" / "model.joblib")
REFERENCE_MANIFEST = str(ROOT / "data" / "processed" / "synthetic_dataset" / "manifest.json")

REQUIRED_FIELDS = {
    "declaration_tva": ["chiffre_affaires_ht", "montant_tva_du", "date"],
    "declaration_is": ["resultat_fiscal", "montant_is_du", "exercice"],
    "avis_redressement": ["montant_rappel", "motif", "reference_dossier"],
    "reclamation": ["montant_conteste", "objet", "reference_imposition"],
    "justificatif": ["montant", "nature"],
}

_classifier = None
_ref_stats = None


@app.on_event("startup")
def startup():
    init_db()
    global _classifier, _ref_stats
    if Path(MODEL_PATH).exists():
        _classifier = DocumentClassifier.load(MODEL_PATH)
    if Path(REFERENCE_MANIFEST).exists():
        _ref_stats = compute_reference_stats(REFERENCE_MANIFEST)


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if _classifier is None:
        raise HTTPException(500, "Modèle de classification non chargé. Entraîne-le d'abord (classifier.py train).")

    # 1. Sauvegarde du fichier
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. OCR
    raw_text = extract_text(str(file_path))

    # 3. Classification
    predicted_type, confidence = _classifier.predict(raw_text)

    # 4. Extraction des champs structurés
    extraction = extract_fields(raw_text)

    # 5. Validation (champs obligatoires manquants pour ce type de document)
    required = REQUIRED_FIELDS.get(predicted_type, [])
    missing = [f for f in required if f not in extraction.fields]

    # 6. Détection d'anomalies sur les montants
    anomalies = []
    if _ref_stats:
        anomalies = flag_anomalies(predicted_type, extraction.fields, _ref_stats)

    record = DocumentRecord(
        filename=file.filename,
        predicted_type=predicted_type,
        prediction_confidence=confidence,
        extracted_fields=extraction.fields,
        missing_fields=missing,
        anomalies=anomalies,
        is_flagged=bool(missing or anomalies),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "predicted_type": predicted_type,
        "confidence": round(confidence, 3),
        "extracted_fields": extraction.fields,
        "missing_fields": missing,
        "anomalies": anomalies,
        "is_flagged": record.is_flagged,
    }


@app.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    records = db.query(DocumentRecord).order_by(DocumentRecord.processed_at.desc()).all()
    return records


@app.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
    if not record:
        raise HTTPException(404, "Document introuvable")
    return record


@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    records = db.query(DocumentRecord).all()
    total = len(records)
    flagged = sum(1 for r in records if r.is_flagged)
    by_type = {}
    for r in records:
        by_type[r.predicted_type] = by_type.get(r.predicted_type, 0) + 1

    return {
        "total_documents": total,
        "flagged_documents": flagged,
        "flagged_rate": round(flagged / total, 3) if total else 0,
        "documents_by_type": by_type,
    }


@app.get("/")
def root():
    return {"status": "GEIF API opérationnelle", "docs": "/docs"}
