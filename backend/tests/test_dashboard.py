"""Étapes 5 et 6 : anomalies, charge à venir, prévision saisonnière, base de connaissances, données AMMC."""
from datetime import datetime, timedelta

import pytest

import app.rag as rag
from app.database import col_documents, col_reclamations


# ----------------------------------------------------------------------------------------------- AMMC
def test_ammc_donnees_reelles_du_depot(client, G):
    d = client.get("/marche-ammc", headers=G).json()
    assert d["disponible"] and d["kpis"]["banques"] == 7 and d["kpis"]["etats_financiers"] == 42
    assert 0 < d["kpis"]["valides"] < d["kpis"]["extraits"] < d["kpis"]["etats_financiers"], "la qualité d'extraction partielle est visible"
    assert {"valide", "partiel", "non_extrait"} <= {l["statut"] for l in d["lignes"]}
    assert all(l["pdf_url"].startswith("https://www.ammc.ma") for l in d["lignes"])
    # fusion correcte entre les deux fichiers (clé société + exercice)
    cdg = next(l for l in d["lignes"] if l["banque"] == "CDG capital" and l["annee"] == 2020)
    assert cdg["statut"] == "valide" and cdg["total_actif"] == 11832.0 and cdg["resultat_net"] == 92.0


def test_ammc_filtres(client, G):
    q = lambda **p: client.get("/marche-ammc", params=p, headers=G).json()
    assert q(banque="BMCI")["total_filtre"] == 6 or q(banque="BMCI")["total_filtre"] > 0
    assert all(l["banque"] == "BMCI" for l in q(banque="BMCI")["lignes"])
    assert all(l["annee"] == 2023 for l in q(annee=2023)["lignes"])
    assert all(l["statut"] == "valide" for l in q(statut="valide")["lignes"])
    assert q(q="attijari")["total_filtre"] > 0 and q(q="zzzzzz")["total_filtre"] == 0
    assert client.get("/marche-ammc", params={"statut": "n'importe quoi"}, headers=G).status_code == 422
    assert client.get("/marche-ammc").status_code in (401, 403)


@pytest.mark.parametrize("nom,attendu", [
    ("Attijariwafa Bank SA", "ATTIJARIWAFA BANK"), ("CIH BANK", "CIH Bank"), ("Banque Centrale Populaire", "Banque Centrale Populaire (BCP)"),
    ("BCP", "Banque Centrale Populaire (BCP)"), ("Crédit du Maroc", "Crédit du Maroc (CDM)"), ("Attijariwafa Bnak", "ATTIJARIWAFA BANK"),
    ("CDG Capital SA", "CDG capital"),
])
def test_rapprochement_reconnait_les_emetteurs(client, G, nom, attendu):
    r = client.get("/marche-ammc/rapprochement", params={"nom": nom}, headers=G).json()
    assert r["correspondance"] and r["emetteur"] == attendu and r["exercices"]


@pytest.mark.parametrize("nom", ["Société Atlas Matériaux SARL", "Boulangerie Al Wafa SARL", "Zenith Conseil SA", "Banque Alimentaire du Sud"])
def test_rapprochement_pas_de_faux_positif(client, G, nom):
    assert client.get("/marche-ammc/rapprochement", params={"nom": nom}, headers=G).json() == {"correspondance": False}


# ------------------------------------------------------------------------------------- Base de connaissances
def test_etat_de_la_base_du_cgi(client, G, monkeypatch):
    import conftest
    monkeypatch.setattr(rag, "_collection_seule", lambda: conftest._FausseCollection())
    rag._etat_cache.update(valeur=None, date=0.0)
    e = client.get("/connaissances/etat", headers=G).json()
    assert e["disponible"] and e["passages"] == 3 and e["articles"] == 3 and (e["page_min"], e["page_max"]) == (12, 120)
    assert e["source"]["nom"] == "CGI.pdf" and e["modele"]
    assert client.get("/connaissances/etat").status_code in (401, 403)


def test_recherche_dans_le_cgi(client, G, monkeypatch):
    import conftest
    monkeypatch.setattr(rag, "_collection_seule", lambda: conftest._FausseCollection())
    r = client.get("/connaissances/recherche", params={"q": "réclamations présentées six mois"}, headers=G).json()
    assert r["disponible"] and r["resultats"] and r["resultats"][0]["article"] == "Article 235" and r["resultats"][0]["pertinent"]
    assert r["resultats"][0]["extrait"].startswith("Article 235")
    # consultation directe d'un article : texte exact, pas de score
    r = client.get("/connaissances/recherche", params={"q": "article 232"}, headers=G).json()
    assert r["consultation_directe"] and r["resultats"][0] == {**r["resultats"][0], "article": "Article 232", "exact": True, "score": None, "pertinent": True}
    assert client.get("/connaissances/recherche", params={"q": "ab"}, headers=G).status_code == 422


# --------------------------------------------------------------------------------------------- Anomalies
def _vieillir(rid, jours):
    col_reclamations.update_one({"_id": rid}, {"$set": {"created_at": (datetime.now() - timedelta(days=jours)).isoformat()}})


def test_anomalies_signalent_les_dossiers_a_verifier(client, G, depot):
    sain, _ = depot(date_mer="2024-01-10", date_reclam="2024-03-01", montant=100000)
    col_documents.insert_one({"reclamation_id": sain, "ocr_ok": True, "texte_ocr": "x", "champs_ocr": {"identifiant_fiscal": "12345601"}})
    tardif, _ = depot(date_mer="2023-01-10", date_reclam="2024-03-01")              # > 180 jours
    faux_if, _ = depot(ifn="99999999")
    col_documents.insert_one({"reclamation_id": faux_if, "ocr_ok": True, "texte_ocr": "x", "champs_ocr": {"identifiant_fiscal": "12345601"}})
    illisible, _ = depot()
    col_documents.insert_one({"reclamation_id": illisible, "ocr_ok": False, "texte_ocr": "", "champs_ocr": {}})
    ancien, _ = depot(); _vieillir(ancien, 30)
    for i in range(5):                                                               # moyenne basse + un montant très élevé
        depot(montant=1000 + i)
    enorme, _ = depot(montant=5_000_000)
    d = client.get("/statistiques/anomalies", headers=G).json()
    par_id = {i["id"]: {s["code"] for s in i["signaux"]} for i in d["items"]}
    assert "delai_depasse" in par_id[tardif]
    assert "if_different" in par_id[faux_if]
    assert "ocr_echec" in par_id[illisible]
    assert "attente_longue" in par_id[ancien]
    assert "montant_atypique" in par_id[enorme]
    assert sain not in par_id, "un dossier cohérent ne doit lever aucun signal"
    assert d["resume"]["delai_depasse"] >= 1 and d["seuils"]["delai_jours"] == 180
    assert d["items"] == sorted(d["items"], key=lambda i: (-len(i["signaux"]), i["created_at"]))
    assert client.get("/statistiques/anomalies").status_code in (401, 403)


# -------------------------------------------------------------------------------------------- Prévisions
def test_charge_a_venir_honnete_sur_la_fiabilite(client, G, depot):
    assert client.get("/predictions/charge", headers=G).json()["disponible"] is False   # pas d'historique
    for jours in (30, 29, 29, 20, 20, 20, 10, 10, 5, 5, 5, 1):
        _vieillir(depot()[0], jours)
    d = client.get("/predictions/charge", params={"horizon_jours": 14}, headers=G).json()
    assert d["disponible"] and d["fiabilite"] == "insuffisante" and "indicative" in d["explication"]
    assert len(d["previsions"]) == 14 and all(p["volume_prevu"] >= 0 for p in d["previsions"])
    assert sum(h["volume"] for h in d["historique"]) == 12, "tous les dépôts sont comptés, jours vides inclus"
    assert any(h["volume"] == 0 for h in d["historique"]) and d["total_prevu_7j"] <= d["total_prevu_horizon"]
    assert client.get("/predictions/charge", params={"tax": "XX"}, headers=G).status_code == 422
    assert client.get("/predictions/charge", params={"tax": "IS"}, headers=G).json()["disponible"] is False


def test_prevision_saisonniere_sur_serie_simulee(client, G, tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "CACHE_DIR", str(tmp_path))
    d = client.get("/predictions/saisonnalite", params={"tax": "TVA", "horizon": 6}, headers=G).json()
    assert d["disponible"] and d["serie_simulee"] is True
    assert len(d["historique"]) >= 24 and len(d["baseline"]) == 6
    assert d["historique"][-1]["mois"] < datetime.now().strftime("%Y-%m"), "l'historique s'arrête au dernier mois complet"
    assert d["baseline"][0]["mois"] == (datetime.now().replace(day=1)).strftime("%Y-%m"), "la prévision commence le mois en cours"
    if d["sarimax"]:
        assert len(d["sarimax"]) == 6 and all(p["bas"] <= p["volume"] <= p["haut"] for p in d["sarimax"])
    assert d["backtest"] and d["backtest"]["meilleur"] in ("SARIMAX", "Baseline saisonnier")
    assert isinstance(d["backtest"]["sarimax_converge"], bool) and "sarimax_converge" in d
    if not d["backtest"]["sarimax_converge"]:
        assert d["backtest"]["meilleur"] == "Baseline saisonnier", "un modèle non convergé ne peut pas être déclaré meilleur"
    # reproductible : la série est mise en cache avec une graine fixe
    assert (tmp_path / "fiscal_timeseries.csv").exists()
    assert client.get("/predictions/saisonnalite", params={"tax": "TP"}, headers=G).status_code == 422


def test_articles_les_plus_mobilises(client, G, CS, depot):
    for _ in range(3):
        rid, _c = depot()
        client.post(f"/reclamations/{rid}/traiter", headers=G)
    s = client.get("/statistiques", headers=CS).json()
    assert s["articles_mobilises"] and s["articles_mobilises"][0]["nombre"] == 3
