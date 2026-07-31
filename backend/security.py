"""
GEIF — Sécurité réelle : authentification JWT + bcrypt + RBAC
===================================================================
Remplace toute vérification "mot de passe en clair côté client" par de la
vraie sécurité côté serveur :

  - Mots de passe hashés avec bcrypt (jamais stockés/comparés en clair)
  - Authentification par token JWT (signé, à durée de vie limitée)
  - RBAC (Role-Based Access Control) : chaque endpoint vérifie le rôle
    contenu dans le token, pas une simple case cochée côté navigateur
  - Rate limiting (anti brute-force) appliqué sur l'endpoint de login

⚠️ SECRET_KEY : à générer une seule fois et stocker dans une variable
d'environnement en production (jamais en dur dans le code versionné).
Ici, une valeur de démo est utilisée si la variable n'est pas définie.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

# =====================================================================
# CONFIGURATION
# =====================================================================
SECRET_KEY = os.environ.get("GEIF_SECRET_KEY", "CHANGE_MOI_EN_PRODUCTION_ceci_est_une_cle_de_demo")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# =====================================================================
# UTILISATEURS ET RÔLES (à terme : table en base, pas en dur)
# -----------------------------------------------------------------
# Les mots de passe ci-dessous sont HASHÉS avec bcrypt (jamais en clair).
# Génère de nouveaux hash avec : hash_password("ton_mot_de_passe")
# =====================================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


FAKE_USERS_DB = {
    "agent1": {
        "username": "agent1",
        "hashed_password": hash_password("agent2026"),
        "role": "agent",
    },
    "souschef1": {
        "username": "souschef1",
        "hashed_password": hash_password("souschef2026"),
        "role": "souschef",
    },
    "chef1": {
        "username": "chef1",
        "hashed_password": hash_password("chef2026"),
        "role": "chef",
    },
}

# Permissions par rôle — vérifiées côté serveur, pas côté client
ROLE_PERMISSIONS = {
    "agent":    {"can_upload": True, "can_validate": False, "can_view_stats": True},
    "souschef": {"can_upload": True, "can_validate": True, "can_view_stats": True},
    "chef":     {"can_upload": True, "can_validate": True, "can_view_stats": True},
}


class TokenData(BaseModel):
    username: str
    role: str


# =====================================================================
# FONCTIONS D'AUTHENTIFICATION
# =====================================================================
def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = FAKE_USERS_DB.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
        return TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception


# =====================================================================
# DÉPENDANCES FASTAPI (à utiliser dans les endpoints avec Depends(...))
# =====================================================================
async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    return decode_token(token)


def require_role(*allowed_roles: str):
    """Factory de dépendance FastAPI : bloque l'accès si le rôle du token
    n'est pas dans la liste autorisée. Vérification 100% côté serveur."""
    async def role_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle '{current_user.role}' non autorisé pour cette action (requis : {allowed_roles})",
            )
        return current_user
    return role_checker


def require_permission(permission: str):
    """Vérifie une permission précise (can_validate, can_upload...) plutôt
    qu'un rôle exact — plus flexible si la liste des rôles évolue."""
    async def permission_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        perms = ROLE_PERMISSIONS.get(current_user.role, {})
        if not perms.get(permission, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' non accordée au rôle '{current_user.role}'",
            )
        return current_user
    return permission_checker
