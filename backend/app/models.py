"""Schémas Pydantic — validation d'entrée et forme des réponses."""
import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .config import settings
from .constants import TAX_TYPES


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    role: str = "gestionnaire"
    registration_code: str | None = None

    def role_valide(self) -> bool:
        return self.role in settings.ROLES

    def code_valide(self) -> tuple[bool, str]:
        """(ok, message_erreur). Un chef sans code configuré dans .env = inscription désactivée."""
        attendu = settings.ROLE_REGISTRATION_CODES.get(self.role, "")
        if not attendu:
            if self.role in settings.ROLES_CODE_OBLIGATOIRE:
                return False, "Inscription désactivée pour ce rôle : aucun code n'est configuré côté serveur (voir .env)."
            return True, ""  # ex : gestionnaire sans code configuré = inscription libre
        if self.registration_code != attendu:
            return False, "Code d'inscription incorrect pour ce rôle — demande-le à l'administrateur du système."
        return True, ""


class LoginRequest(BaseModel):
    username: str
    password: str


class NouvelleReclamation(BaseModel):
    contrib: str = Field(min_length=2, max_length=200)             # raison sociale
    ifn: str = Field(min_length=3, max_length=30)                  # identifiant fiscal
    tax: str                                                       # IS | IR | TVA
    motif: str = Field(min_length=3, max_length=300)               # objet de la réclamation
    montant: float = Field(gt=0)                                   # montant contesté
    date_mer: str      # ISO — date de mise en recouvrement
    date_reclam: str   # ISO — date de la réclamation
    email: str | None = None      # requis pour recevoir la décision finale par e-mail
    telephone: str | None = Field(default=None, max_length=30)

    @field_validator("tax")
    @classmethod
    def _tax(cls, v):
        if v not in TAX_TYPES:
            raise ValueError(f"Type d'impôt invalide (attendu : {', '.join(TAX_TYPES)}).")
        return v

    @field_validator("date_mer", "date_reclam")
    @classmethod
    def _date(cls, v):
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("Date invalide (format attendu : AAAA-MM-JJ).")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if v in (None, ""):
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Adresse e-mail invalide.")
        return v


class DecisionGestionnaire(BaseModel):
    outcome: Optional[str] = None  # accept | reject  (obligatoire sur /decision)
    decision_finale: Optional[str] = None
    rapport_finale: Optional[str] = None
    type_decision: Optional[str] = None  # Rejet | Dégrèvement total | Dégrèvement partiel


class ValidationChef(BaseModel):
    outcome: Literal["accept", "return"]
    commentaire: Optional[str] = Field(default=None, max_length=1000)  # obligatoire si "return"


class AssistantMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AssistantSitRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    historique: Optional[list[AssistantMessage]] = None


class ReformulationRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=300)


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    gestionnaire_destinataire: str | None = None  # rempli par le contribuable au premier message


class PredictionVolumeRequest(BaseModel):
    tax: Optional[str] = None       # None = toutes taxes confondues
    horizon_jours: int = Field(default=7, ge=1, le=90)


class PredictionOutcomeRequest(BaseModel):
    tax: str
    motif: str
    montant: float
    date_mer: str
    date_reclam: str
