"""Tests du circuit complet : dépôt -> traitement -> validations -> décision -> historique."""
import io

from PIL import Image, ImageDraw, ImageFont


def _png_texte(texte="Identifiant fiscal : 12345601  Montant 100 000,00 DH"):
    img = Image.new("RGB", (1100, 140), "white")
    ImageDraw.Draw(img).text((20, 40), texte, fill="black", font=ImageFont.load_default(size=34))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _liste(client, headers, **params):
    r = client.get("/reclamations", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_depot_validation(client):
    base = {"contrib": "X SARL", "ifn": "123456", "tax": "TVA", "motif": "Erreur de taux", "montant": 10,
            "date_mer": "2024-01-10", "date_reclam": "2024-03-01"}
    assert client.post("/reclamations", json={**base, "tax": "TP"}).status_code == 422
    assert client.post("/reclamations", json={**base, "montant": -5}).status_code == 422
    assert client.post("/reclamations", json={**base, "date_mer": "10/01/2024"}).status_code == 422
    assert client.post("/reclamations", json={**base, "email": "pas-un-email"}).status_code == 422
    assert client.post("/reclamations", json={**base, "date_reclam": "2023-01-01"}).status_code == 422
    assert client.post("/reclamations", json=base).status_code == 200


def test_signup_codes(client):
    r = client.post("/auth/signup", json={"username": "boss", "password": "motdepasse1", "role": "chef_service", "registration_code": "faux"})
    assert r.status_code == 403
    r = client.post("/auth/signup", json={"username": "boss", "password": "motdepasse1", "role": "chef_secteur"})
    assert r.status_code == 400  # ancien rôle supprimé


def test_nouvelle_arrive_sur_accueil_gestionnaire_seulement(client, G, CS, CSUB, depot):
    rid, _ = depot()
    assert [i["id"] for i in _liste(client, G)["items"]] == [rid]
    assert _liste(client, G)["items"][0]["status"] == "nouvelle"
    assert _liste(client, CS)["total"] == 0 and _liste(client, CSUB)["total"] == 0
    assert client.get("/reclamations").status_code in (401, 403)  # pas de connexion


def test_circuit_complet_avec_retour(client, G, CS, CSUB, depot):
    rid, cle = depot()

    # permissions
    assert client.post(f"/reclamations/{rid}/traiter", headers=CS).status_code == 403
    assert client.post(f"/reclamations/{rid}/decision", json={"outcome": "accept"}, headers=G).status_code == 409  # pas encore traité

    # Traiter : RAG + texte (repli sans Groq)
    t = client.post(f"/reclamations/{rid}/traiter", headers=G)
    assert t.status_code == 200, t.text
    t = t.json()
    assert t["status"] == "en_traitement" and t["rapport"] and t["decision"]
    assert t["type_decision"] in ("Rejet", "Dégrèvement total", "Dégrèvement partiel")
    arts = [a["article"] for a in t["articles_rag"]]
    assert arts and len(arts) == len(set(arts))        # un seul chunk par article
    assert client.get(f"/reclamations/{rid}", headers=G).json()["status"] == "en_traitement"

    # rouvrir ne régénère pas (le texte du gestionnaire est conservé)
    client.post(f"/reclamations/{rid}/brouillon", json={"decision_finale": "Texte édité par le gestionnaire"}, headers=G)
    t2 = client.post(f"/reclamations/{rid}/traiter", headers=G).json()
    assert t2["decision"] == "Texte édité par le gestionnaire"

    # Gestionnaire envoie
    r = client.post(f"/reclamations/{rid}/decision", json={"outcome": "accept"}, headers=G)
    assert r.status_code == 200 and r.json()["status"] == "envoyee_chef_service" and r.json()["feedback"] == "modify"
    assert _liste(client, G)["total"] == 0                       # sort de l'accueil du gestionnaire
    assert [i["id"] for i in _liste(client, CS)["items"]] == [rid]

    # Chef de Service : retour sans commentaire refusé, puis avec commentaire
    assert client.post(f"/reclamations/{rid}/decision-service", json={"outcome": "return"}, headers=CS).status_code == 422
    assert client.post(f"/reclamations/{rid}/decision-subdivision", json={"outcome": "accept"}, headers=CSUB).status_code == 409
    r = client.post(f"/reclamations/{rid}/decision-service", json={"outcome": "return", "commentaire": "Précisez la base légale."}, headers=CS)
    assert r.json()["status"] == "retournee"
    item = _liste(client, G)["items"][0]
    assert item["status"] == "retournee" and item["commentaire_retour"] == "Précisez la base légale."

    # Le gestionnaire reprend (texte conservé), renvoie
    t3 = client.post(f"/reclamations/{rid}/traiter", headers=G).json()
    assert t3["status"] == "en_traitement" and t3["decision"] == "Texte édité par le gestionnaire"
    client.post(f"/reclamations/{rid}/brouillon", json={"rapport_finale": "Rapport complété avec la base légale."}, headers=G)
    assert client.post(f"/reclamations/{rid}/decision", json={"outcome": "accept"}, headers=G).status_code == 200

    # Chef de Service valide -> Chef de Subdivision
    assert client.post(f"/reclamations/{rid}/decision-service", json={"outcome": "accept"}, headers=CS).json()["status"] == "envoyee_chef_subdivision"
    assert _liste(client, CS)["total"] == 0
    assert [i["id"] for i in _liste(client, CSUB)["items"]] == [rid]

    # Chef de Subdivision valide : décision envoyée
    r = client.post(f"/reclamations/{rid}/decision-subdivision", json={"outcome": "accept"}, headers=CSUB)
    assert r.json()["status"] == "decision_envoyee"

    # Il quitte l'accueil de TOUS les rôles, mais reste dans l'historique (pour les 3)
    for h in (G, CS, CSUB):
        assert _liste(client, h)["total"] == 0
        hist = _liste(client, h, scope="historique")
        assert [i["id"] for i in hist["items"]] == [rid]
    assert _liste(client, CS, scope="historique", q="atlas")["total"] == 1
    assert _liste(client, CS, scope="historique", q="zzz")["total"] == 0
    assert _liste(client, CS, scope="historique", tax="IS")["total"] == 0

    # Journal complet
    d = client.get(f"/reclamations/{rid}", headers=CS).json()
    vers = [e["vers"] for e in d["historique"]]
    assert vers == ["nouvelle", "en_traitement", "envoyee_chef_service", "retournee", "en_traitement",
                    "envoyee_chef_service", "envoyee_chef_subdivision", "decision_envoyee"]
    assert d["closed_at"] and d["decision_finale"] == d["decision"]
    assert "cle_verification" not in d and "contenu_b64" not in d

    # Suivi contribuable : décision visible, frise complète
    s = client.get(f"/reclamations/suivi/{rid}", params={"cle": cle}).json()
    assert s["decision_disponible"] and s["decision"] and all(e["etat"] == "fait" for e in s["etapes"])
    assert "par" not in s["evenements"][0]  # aucun nom d'agent exposé
    assert client.post(f"/reclamations/{rid}/lu", params={"cle": cle}).json() == {"lu": True}

    compteurs = client.get("/reclamations/compteurs", headers=G).json()
    assert compteurs["accueil"] == 0 and compteurs["historique"] == 1


def test_reject_gestionnaire_ne_cloture_pas(client, G, CS, depot):
    rid, _ = depot()
    client.post(f"/reclamations/{rid}/traiter", headers=G)
    client.post(f"/reclamations/{rid}/brouillon", json={"decision_finale": "Décision rédigée à la main", "type_decision": "Rejet"}, headers=G)
    r = client.post(f"/reclamations/{rid}/decision", json={"outcome": "reject"}, headers=G).json()
    assert r["status"] == "envoyee_chef_service" and r["feedback"] == "reject"
    from app.database import col_feedback_log
    assert col_feedback_log.count_documents({"outcome": "reject"}) == 1


def test_suivi_exige_reference_et_code(client, G, depot):
    rid, cle = depot()
    assert client.get(f"/reclamations/suivi/{rid}").status_code == 422             # code manquant
    assert client.get(f"/reclamations/suivi/{rid}", params={"cle": "XXXX-XXXX"}).status_code == 404
    assert client.get("/reclamations/suivi/REC-inconnu", params={"cle": cle}).status_code == 404
    ok = client.get(f"/reclamations/suivi/{rid}", params={"cle": cle.lower()}).json()   # insensible à la casse
    assert ok["status"] == "nouvelle" and ok["etapes"][0]["etat"] == "en_cours" and ok["decision"] is None
    assert [e["etat"] for e in ok["etapes"]] == ["en_cours", "a_venir", "a_venir", "a_venir", "a_venir"]


def test_suivi_bloque_le_brute_force(client, depot):
    rid, _ = depot()
    codes = [client.get(f"/reclamations/suivi/{rid}", params={"cle": f"AAAA-{i:04d}"}).status_code for i in range(17)]
    assert codes[:15] == [404] * 15 and codes[15] == 429


def test_documents_protegés_par_la_cle(client, G, depot):
    rid, cle = depot()
    png = _png_texte()
    fichiers = {"demande_degrevement": ("demande.png", png, "image/png")}
    data = {"description_demande": "Demande de dégrèvement"}
    assert client.post(f"/reclamations/{rid}/documents", data={**data, "cle": "AAAA-BBBB"}, files=fichiers).status_code == 403
    r = client.post(f"/reclamations/{rid}/documents", data={**data, "cle": cle}, files=fichiers)
    assert r.status_code == 200, r.text
    assert r.json()["documents_enregistres"][0]["ocr_ok"] is True
    assert client.post(f"/reclamations/{rid}/documents", data={**data, "cle": cle}, files=fichiers).status_code == 409  # déjà déposé

    docs = client.get(f"/reclamations/{rid}/documents", headers=G).json()
    assert docs[0]["champs_ocr"].get("identifiant_fiscal") == "12345601"
    assert "contenu_b64" not in docs[0]
    f = client.get(f"/reclamations/{rid}/documents/{docs[0]['id']}/fichier", headers=G)
    assert f.status_code == 200 and f.headers["content-type"] == "image/png" and f.content == png
    assert client.get(f"/reclamations/{rid}/documents/{docs[0]['id']}/fichier").status_code in (401, 403)

    # le texte lu alimente le traitement
    assert client.post(f"/reclamations/{rid}/traiter", headers=G).json()["pieces_lisibles"] == 1


def test_format_refuse(client, depot):
    rid, cle = depot()
    r = client.post(f"/reclamations/{rid}/documents", data={"description_demande": "x", "cle": cle},
                    files={"demande_degrevement": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_statistiques_et_authentification(client, G, CS, CSUB, depot):
    assert client.get("/statistiques").status_code in (401, 403)
    rid, _ = depot()
    client.post(f"/reclamations/{rid}/traiter", headers=G)
    client.post(f"/reclamations/{rid}/decision", json={"outcome": "accept"}, headers=G)
    client.post(f"/reclamations/{rid}/decision-service", json={"outcome": "accept"}, headers=CS)
    client.post(f"/reclamations/{rid}/decision-subdivision", json={"outcome": "accept"}, headers=CSUB)
    s = client.get("/statistiques", headers=CS).json()
    assert s["total_reclamations"] == 1 and s["terminees"] == 1
    assert sum(s["repartition_decisions"].values()) == 1
    assert s["delai_moyen_traitement_jours"] is not None
    assert s["par_statut"]["decision_envoyee"] == 1
    assert s["feedback_gestionnaire"]["accept"] == 1


def test_migration_anciennes_donnees(client):
    from app.database import col_reclamations, col_users
    from app.migration import migrer
    col_users.insert_one({"username": "old", "password_hash": b"x", "role": "chef_secteur"})
    for i, st in enumerate(["nouvelle", "attente", "attente_chef_secteur", "attente_chef_subdivision", "validee_finale", "rejetee"]):
        col_reclamations.insert_one({"_id": f"R{i}", "status": st, "created_at": "2025-01-01T10:00:00"})
    bilan = migrer()
    assert bilan["roles"] == 1 and bilan["statuts"] == 5 and bilan["historiques"] == 6
    got = {d["_id"]: d["status"] for d in col_reclamations.find()}
    assert got == {"R0": "nouvelle", "R1": "en_traitement", "R2": "envoyee_chef_service",
                   "R3": "envoyee_chef_subdivision", "R4": "decision_envoyee", "R5": "retournee"}
    assert col_users.find_one({"username": "old"})["role"] == "chef_service"
    assert col_reclamations.find_one({"_id": "R4"})["closed_at"]
    assert migrer() == {"roles": 0, "statuts": 0, "historiques": 0}  # idempotent
