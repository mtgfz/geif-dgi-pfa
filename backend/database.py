"""
Connexion MongoDB centralisée + création des index.
Un seul client Mongo pour toute l'application (réutilisé par tous les routers).
"""
from pymongo import MongoClient, ASCENDING, DESCENDING
from .config import settings

_client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=4000)
db = _client[settings.MONGO_DB_NAME]

col_users = db["users"]
col_reclamations = db["reclamations"]
col_rules = db["rules"]
col_corrections = db["corrections"]
col_predictions_log = db["predictions_log"]  # historique des prédictions vs réalité (pour évaluer le modèle)
col_feedback_log = db["feedback_log"]  # TOUTES les décisions (accept/modify/reject) — base de la courbe d'apprentissage
col_documents = db["documents"]  # pièces jointes déposées via le portail SIT (contenu + texte OCR)
col_messages = db["messages"]  # fil de discussion contribuable ↔ gestionnaire, par réclamation


def ping() -> bool:
    try:
        _client.admin.command("ping")
        return True
    except Exception:
        return False


def init_indexes():
    col_users.create_index("username", unique=True)
    col_reclamations.create_index([("created_at", DESCENDING)])
    col_reclamations.create_index("status")
    col_reclamations.create_index("tax")
    col_corrections.create_index([("rule_id", ASCENDING), ("created_at", DESCENDING)])
    col_documents.create_index("reclamation_id")
    col_messages.create_index([("reclamation_id", ASCENDING), ("created_at", ASCENDING)])


def sans_id_mongo(doc: dict) -> dict:
    """Retire le champ _id (spécifique Mongo) avant de renvoyer au frontend.
    cle_verification n'est JAMAIS renvoyée ici : c'est un secret côté
    contribuable, communiqué uniquement par e-mail à la création — même le
    personnel interne n'en a pas besoin pour son propre travail."""
    d = dict(doc)
    d.pop("_id", None)
    d.pop("password_hash", None)
    d.pop("cle_verification", None)
    d.pop("contenu_b64", None)
    return d
