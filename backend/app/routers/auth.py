from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from ..database import col_users, sans_id_mongo
from ..models import LoginRequest, SignupRequest
from ..security import creer_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup")
def signup(body: SignupRequest):
    if not body.role_valide():
        raise HTTPException(400, "Rôle invalide. Valeurs autorisées : gestionnaire, chef_secteur, chef_subdivision.")
    if not body.code_valide():
        raise HTTPException(403, "Code d'inscription incorrect pour ce rôle — demande-le à l'administrateur du système.")
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


@router.post("/login")
def login(body: LoginRequest):
    user = col_users.find_one({"username": body.username})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Identifiants incorrects.")
    token = creer_token(user["username"], user.get("role", "gestionnaire"))
    return {"access_token": token, "token_type": "bearer", "role": user.get("role", "gestionnaire")}


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
