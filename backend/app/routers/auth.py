from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from ..constants import ROLES
from ..database import col_users, sans_id_mongo
from ..models import LoginRequest, SignupRequest
from ..ratelimit import limite
from ..security import creer_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", dependencies=[Depends(limite("signup", 10, 3600))])
def signup(body: SignupRequest):
    if not body.role_valide():
        raise HTTPException(400, f"Rôle invalide. Valeurs autorisées : {', '.join(ROLES)}.")
    ok, message = body.code_valide()
    if not ok:
        raise HTTPException(403, message)
    doc = {
        "username": body.username,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "created_at": datetime.now().isoformat(),
    }
    try:
        col_users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Ce nom d'utilisateur existe déjà.")
    return {"message": "Compte créé avec succès.", "username": body.username, "role": body.role}


@router.post("/login", dependencies=[Depends(limite("login", 10, 300))])
def login(body: LoginRequest):
    user = col_users.find_one({"username": body.username})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Identifiants incorrects.")
    role = user.get("role", "gestionnaire")
    token = creer_token(user["username"], role)
    return {"access_token": token, "token_type": "bearer", "role": role, "username": user["username"]}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    doc = col_users.find_one({"username": user["username"]})
    return sans_id_mongo(doc)


@router.get("/gestionnaires")
def lister_gestionnaires():
    """Public — permet au contribuable de choisir à qui adresser son message
    dans l'espace de discussion du portail SIT. Ne renvoie que le username,
    rien de sensible."""
    rows = col_users.find({"role": "gestionnaire"}, {"username": 1})
    return [r["username"] for r in rows]
