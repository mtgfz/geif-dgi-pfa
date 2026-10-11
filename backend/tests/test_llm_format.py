"""Régression : le modèle de langage répond rarement avec le format exact « RAPPORT: … DECISION: … ».
Avant la correction, la décision restait vide, la page « Traiter » ne montrait rien et chaque clic recommençait."""
import pytest

import app.routers.reclamations as rr
from app.llm import separer_rapport_decision

RAPPORT = "I. Motifs\nLe dossier invoque une erreur de calcul.\n\nIV. Avis de l'inspecteur\nUn dégrèvement partiel est proposé."
DECISION = "Dégrèvement partiel de 12 000 DH accordé conformément à l'Art. 235 CGI."


@pytest.mark.parametrize("sortie", [
    f"RAPPORT:\n{RAPPORT}\nDECISION:\n{DECISION}",                       # format demandé
    f"RAPPORT:\n{RAPPORT}\nDÉCISION :\n{DECISION}",                      # accent + espace avant « : »
    f"**RAPPORT**:\n{RAPPORT}\n\n**DÉCISION :** {DECISION}",             # markdown gras
    f"## Rapport d'instruction :\n{RAPPORT}\n\n### Décision proposée :\n{DECISION}",  # titres markdown
    f"Rapport : {RAPPORT}\nDécision : {DECISION}",                       # minuscules
    f"RAPPORT:\n{RAPPORT}\nDécision contestée : sans objet ici\nDECISION:\n{DECISION}",  # « Décision contestée : » n'est pas un marqueur
])
def test_formats_reels_du_modele(sortie):
    rapport, decision = separer_rapport_decision(sortie)
    assert decision.endswith("Art. 235 CGI.") and "Dégrèvement partiel" in decision
    assert "Avis de l'inspecteur" in rapport and "DÉCISION" not in rapport.upper().replace("DÉCISION CONTESTÉE", "")


def test_sans_marqueur_decision_vide():
    rapport, decision = separer_rapport_decision("Voici simplement un paragraphe de texte sans structure.")
    assert decision == "" and rapport.startswith("Voici")
    assert separer_rapport_decision("") == ("", "")


def _traiter_avec(client, G, depot, monkeypatch, sortie_llm, source="groq_llm"):
    monkeypatch.setattr(rr, "generer_texte_llm", lambda *a, **k: (sortie_llm, source))
    rid, _ = depot()
    r = client.post(f"/reclamations/{rid}/traiter", headers=G)
    assert r.status_code == 200, r.text
    return rid, r.json()


def test_traiter_avec_un_format_non_standard_donne_rapport_et_decision(client, G, depot, monkeypatch):
    rid, t = _traiter_avec(client, G, depot, monkeypatch, f"**RAPPORT**\n{RAPPORT}\n\n**DÉCISION :** {DECISION}")
    assert t["decision"].startswith("Dégrèvement partiel de 12 000 DH") and "Avis de l'inspecteur" in t["rapport"]
    assert t["source_texte"] == "groq_llm"
    # le gestionnaire peut aller au bout : envoi au Chef de Service
    assert client.post(f"/reclamations/{rid}/decision", json={"outcome": "accept"}, headers=G).status_code == 200


def test_reponse_sans_decision_est_completee_par_les_regles(client, G, depot, monkeypatch):
    rid, t = _traiter_avec(client, G, depot, monkeypatch, "Un long texte libre du modèle, sans aucun marqueur de décision.")
    assert t["rapport"] and t["decision"].strip(), "la décision ne doit JAMAIS rester vide"
    assert t["source_texte"] == "groq_llm_decision_repli"
    assert "Art." in t["decision"] or "DH" in t["decision"]


def test_migration_repare_les_dossiers_deja_casses(client, G, depot):
    from app.database import col_reclamations
    from app.migration import migrer
    rid, _ = depot()
    client.post(f"/reclamations/{rid}/traiter", headers=G)
    # état laissé par l'ancien code : tout le texte dans « rapport », décision vide
    col_reclamations.update_one({"_id": rid}, {"$set": {"rapport": f"RAPPORT:\n{RAPPORT}\n**DÉCISION :** {DECISION}", "decision": ""}})
    assert migrer()["decisions"] == 1
    d = client.get(f"/reclamations/{rid}", headers=G).json()
    assert d["decision"] == DECISION and "DÉCISION" not in d["rapport"].upper()
    assert migrer()["decisions"] == 0   # idempotent
