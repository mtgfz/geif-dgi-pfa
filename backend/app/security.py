"""
Sécurité : hashage des mots de passe (bcrypt), émission/vérification de JWT,
et dépendances FastAPI pour protéger les routes (authentification + rôles).
"""
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .database import col_users

security_scheme = HTTPBearer()
security_scheme_optional = HTTPBearer(auto_error=False)


# ---------- mots de passe ----------

def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


def verify_password(password: str, password_hash: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash)


# ---------- JWT ----------

def creer_token(username: str, role: str) -> str:
    expiration = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    payload = {"sub": username, "role": role, "exp": expiration}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGO)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expirée, reconnectez-vous.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Jeton invalide.")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> dict:
    """Retourne {"username":..., "role":...} — lève 401 si le token est invalide/expiré,
    ou si l'utilisateur a été supprimé depuis l'émission du token."""
    payload = _decode(credentials.credentials)
    username = payload["sub"]
    user = col_users.find_one({"username": username})
    if not user:
        raise HTTPException(401, "Utilisateur introuvable — reconnectez-vous.")
    return {"username": username, "role": user.get("role", "gestionnaire")}


def get_current_user_optional(credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme_optional)) -> dict | None:
    """Comme get_current_user, mais renvoie None au lieu de lever 401 quand
    aucun jeton n'est fourni — pour les routes accessibles soit avec un
    compte interne, soit avec un autre secret (ex: la clé de vérification
    du contribuable)."""
    if credentials is None:
        return None
    try:
        return get_current_user(credentials)
    except HTTPException:
        return None


def require_roles(*roles: str):
    """Dépendance paramétrable : require_roles("chef_secteur", "chef_subdivision")
    restreint une route aux rôles listés. Sans argument, authentifie seulement."""
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if roles and user["role"] not in roles:
            raise HTTPException(
                403,
                f"Action réservée à : {', '.join(roles)} (rôle actuel : {user['role']}).",
            )
        return user
    return _dep
