"""
Données de démonstration (fictives) pour voir l'application remplie.

    cd backend
    python seed_demo.py            # refuse si des réclamations existent déjà
    python seed_demo.py --force    # ajoute quand même

Crée 3 comptes de démo (mot de passe : Demo2026!) :
    demo_gestionnaire / demo_chef_service / demo_chef_subdivision
et 9 réclamations à différents stades (nouvelles, en traitement, retournée, en validation, décisions envoyées).
Aucun e-mail n'est envoyé et Groq n'est pas appelé (textes de repli) : sans effet de bord externe.
À NE PAS utiliser en production (comptes à mot de passe connu) : supprime les comptes demo_* ensuite.
"""
import io
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.database import col_reclamations, col_users
from app.security import hash_password

PASSWORD = "Demo2026!"
USERS = [("demo_gestionnaire", "gestionnaire"), ("demo_chef_service", "chef_service"), ("demo_chef_subdivision", "chef_subdivision")]
DEMO = [  # raison sociale, IF, impôt, motif, montant, statut visé, ancienneté (jours)
    ("Société Atlas Matériaux SARL", "12345601", "TVA", "Contestation d'un rappel de TVA sur les achats de 2023", 184500, "nouvelle", 0),
    ("Zenith Conseil SA", "12345602", "IS", "Double imposition de l'IS sur l'exercice 2022", 920000, "nouvelle", 1),
    ("Maghreb Logistique SARL", "12345603", "IR", "Base de calcul de la retenue à la source contestée", 56000, "en_traitement", 4),
    ("Boulangerie Al Wafa SARL", "12345604", "IR", "Erreur sur la base imposable des revenus professionnels", 23800, "retournee", 6),
    ("Cosmetica Rabat SA", "12345605", "TVA", "Refus de remboursement du crédit de TVA", 410000, "envoyee_chef_service", 5),
    ("Bati-Sud Promotion SA", "12345606", "IS", "Réintégration de charges non déductibles contestée", 1250000, "envoyee_chef_subdivision", 8),
    ("Textile Oasis SARL", "12345607", "TVA", "Pénalités de retard malgré une déclaration dans les délais", 78200, "decision_envoyee", 20),
    ("Clinique Les Orangers SA", "12345608", "IR", "Redressement sur les revenus professionnels", 132000, "decision_envoyee", 35),
    ("Agro Souss Export SA", "12345609", "IS", "Dégrèvement demandé suite à une erreur de liquidation", 310000, "decision_envoyee", 12),
]


def _png() -> bytes:
    img = Image.new("RGB", (1100, 140), "white")
    try:
        font = ImageFont.load_default(size=34)
    except TypeError:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((20, 40), "Demande de degrevement - Identifiant fiscal : 12345601", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def run(force: bool = False) -> int:
    if col_reclamations.count_documents({}) > 0 and not force:
        print("Des réclamations existent déjà : rien n'est ajouté (utilise --force pour ajouter quand même).")
        return 1
    settings.GROQ_API_KEY = ""   # pas d'appel externe pendant la démo
    settings.SMTP_HOST = ""      # pas d'e-mail pendant la démo

    from fastapi.testclient import TestClient  # import tardif : nécessite httpx (requirements-dev.txt)
    import main

    for username, role in USERS:
        if not col_users.find_one({"username": username}):
            col_users.insert_one({"username": username, "password_hash": hash_password(PASSWORD), "role": role,
                                  "created_at": datetime.now().isoformat()})
    with TestClient(main.app) as c:
        tok = {}
        for username, role in USERS:
            r = c.post("/auth/login", json={"username": username, "password": PASSWORD})
            if r.status_code != 200:
                print(f"Connexion impossible pour {username} : {r.text}")
                return 1
            tok[role] = {"Authorization": "Bearer " + r.json()["access_token"]}
        G, CS, CSUB = tok["gestionnaire"], tok["chef_service"], tok["chef_subdivision"]
        for name, ifn, tax, motif, montant, cible, jours in DEMO:
            r = c.post("/reclamations", json={"contrib": name, "ifn": ifn, "tax": tax, "motif": motif, "montant": montant,
                                              "date_mer": "2024-01-10", "date_reclam": "2024-03-01"}).json()
            rid, cle = r["id"], r["cle_verification"]
            if cible != "nouvelle" and cible != "en_traitement" or name.startswith("Maghreb"):
                c.post(f"/reclamations/{rid}/documents", data={"cle": cle, "description_demande": "Demande de dégrèvement"},
                       files={"demande_degrevement": ("demande.png", _png(), "image/png")})
            if cible != "nouvelle":
                c.post(f"/reclamations/{rid}/traiter", headers=G)
            if cible in ("envoyee_chef_service", "retournee", "envoyee_chef_subdivision", "decision_envoyee"):
                c.post(f"/reclamations/{rid}/decision", json={"outcome": "accept"}, headers=G)
            if cible == "retournee":
                c.post(f"/reclamations/{rid}/decision-service", json={"outcome": "return",
                       "commentaire": "Merci de préciser la base légale et de joindre la pièce manquante."}, headers=CS)
            if cible in ("envoyee_chef_subdivision", "decision_envoyee"):
                c.post(f"/reclamations/{rid}/decision-service", json={"outcome": "accept"}, headers=CS)
            if cible == "decision_envoyee":
                c.post(f"/reclamations/{rid}/decision-subdivision", json={"outcome": "accept"}, headers=CSUB)
                col_reclamations.update_one({"_id": rid}, {"$set": {
                    "closed_at": (datetime.now() - timedelta(days=max(jours - 15, 1))).isoformat(),
                    "created_at": (datetime.now() - timedelta(days=jours)).isoformat()}})
            else:
                col_reclamations.update_one({"_id": rid}, {"$set": {"created_at": (datetime.now() - timedelta(days=jours)).isoformat()}})
            print(f"  {rid}  code={cle}  {name}  → {cible}")
    print(f"\nTerminé. Comptes de démo (mot de passe {PASSWORD}) : " + ", ".join(u for u, _ in USERS))
    return 0


if __name__ == "__main__":
    sys.exit(run(force="--force" in sys.argv))
