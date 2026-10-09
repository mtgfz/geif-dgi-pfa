"""
Configuration centralisée — charge backend/.env et expose les paramètres
utilisés par tous les autres modules. Un seul point de vérité, donc un seul
endroit à changer pour passer de la démo locale à un vrai déploiement.
"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)


class Settings:
    # --- Base de données ---
    MONGO_URI: str = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.environ.get("MONGO_DB_NAME", "geif_reclamations")

    # --- Sécurité / JWT ---
    JWT_SECRET: str = os.environ.get("JWT_SECRET") or os.urandom(32).hex()
    JWT_ALGO: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = int(os.environ.get("JWT_EXPIRATION_MINUTES", "120"))

    # --- LLM (Groq) ---
    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
    GROQ_URL: str = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

    # --- RAG ---
    CHROMA_PATH: str = os.environ.get(
        "CHROMA_PATH",
        os.path.join(os.path.dirname(__file__), "..", "..", "rag", "chroma_db"),
    )
    EMBED_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2"
    SEUIL_CONFIANCE_RETRIEVAL: int = 2

    # --- CORS ---
    ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

    # --- Email (SMTP réel) ---
    # Exemple avec Gmail : SMTP_HOST=smtp.gmail.com, SMTP_PORT=587,
    # SMTP_USER=ton.adresse@gmail.com, SMTP_PASSWORD=un "mot de passe
    # d'application" généré sur myaccount.google.com/apppasswords
    # (le mot de passe normal du compte NE fonctionnera PAS).
    SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER: str = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.environ.get("SMTP_FROM", "") or SMTP_USER
    SMTP_FROM_NAME: str = os.environ.get("SMTP_FROM_NAME", "DGI — GEIF (Espace Contribuable)")

    def email_configure(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)

    # --- Rôles reconnus par le système (hiérarchie DGI) ---
    ROLES = ("gestionnaire", "chef_secteur", "chef_subdivision")

    # --- Codes d'inscription par rôle (en plus du mot de passe) ---
    # Un rôle absent de ce dict (ex: "gestionnaire") ne demande aucun code.
    # Change ces valeurs dans .env avant la démo — ce sont celles que tu
    # communiques toi-même à la personne qui s'inscrit sous ce rôle.
    ROLE_REGISTRATION_CODES = {
        "chef_secteur": os.environ.get("CODE_CHEF_SECTEUR", "SECTEUR-2026"),
        "chef_subdivision": os.environ.get("CODE_CHEF_SUBDIVISION", "SUBDIVISION-2026"),
    }

    # --- OCR (Tesseract local) ---
    # Sous Windows, Tesseract n'est généralement pas dans le PATH : indique le
    # chemin complet de tesseract.exe ici (ex: après installation via
    # https://github.com/UB-Mannheim/tesseract/wiki, souvent
    # "C:\\Program Files\\Tesseract-OCR\\tesseract.exe").
    TESSERACT_CMD: str = os.environ.get("TESSERACT_CMD", "")
    OCR_LANGS: str = os.environ.get("OCR_LANGS", "fra+ara")  # français + arabe

    # --- Documents (portail SIT) ---
    DOCUMENT_TYPES_AUTORISES = {"application/pdf", "image/png", "image/jpeg"}
    DOCUMENT_TAILLE_MAX_MO = 10
    DOCUMENT_MAX_OPTIONNELS = 5
    DOCUMENT_DESCRIPTION_MAX = 50

    # --- Prédiction / apprentissage ---
    # Probabilité d'exploration (epsilon-greedy) : de temps en temps, le système
    # applique la règle la mieux notée MAIS garde une petite marge d'incertitude
    # affichée au gestionnaire plutôt que de figer aveuglément sur l'historique.
    EXPLORATION_EPSILON: float = float(os.environ.get("EXPLORATION_EPSILON", "0.05"))


settings = Settings()

if settings.JWT_SECRET is None or len(settings.JWT_SECRET) < 16:
    raise RuntimeError(
        "JWT_SECRET manquant ou trop court — définis-le dans backend/.env "
        "(voir .env.example)."
    )
