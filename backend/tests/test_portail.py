"""API publique du portail contribuable : motifs, période, assistant appuyé sur le CGI."""
import app.llm as llm


def test_motifs_publics_alignes_sur_les_regles(client):
    r = client.get("/reclamations/motifs")           # public : pas de connexion
    assert r.status_code == 200
    m = r.json()
    assert set(m) == {"IS", "IR", "TVA"}
    assert "Double imposition" in m["IS"] and "TVA déductible non prise en compte" in m["TVA"]
    assert all(len(v) >= 3 for v in m.values())
    # chaque motif proposé correspond EXACTEMENT à une règle (sinon le moteur retomberait sur une règle par défaut)
    from app.rules_engine import RULES
    assert all(any(x["tax"] == t and x["motif"] == mo for x in RULES.values()) for t, ms in m.items() for mo in ms)


def test_periode_enregistree_et_visible_des_agents(client, G, depot):
    rid, _ = depot(periode="  Exercice 2023 ")
    assert client.get(f"/reclamations/{rid}", headers=G).json()["periode"] == "Exercice 2023"
    rid2, _ = depot()  # facultative
    assert client.get(f"/reclamations/{rid2}", headers=G).json()["periode"] is None


def test_assistant_s_appuie_sur_le_cgi_et_cite_ses_sources(client, monkeypatch):
    vus = {}

    def faux_groq(prompt, **kw):
        vus["prompt"] = prompt
        return "Le délai est de six mois (Art. 235 CGI)."
    monkeypatch.setattr(llm, "_appeler_groq", faux_groq)
    r = client.post("/assistant/sit", json={"question": "Dans quel délai les réclamations doivent-elles être présentées ? six mois"})
    assert r.status_code == 200
    d = r.json()
    assert d["genere"] is True and "Art. 235" in d["reponse"]
    assert any(s["article"] == "Art. 235 CGI" for s in d["sources"])
    assert "EXTRAITS DU CGI" in vus["prompt"] and "six mois" in vus["prompt"]          # le RAG alimente bien le prompt
    assert "N'invente JAMAIS" in vus["prompt"]


def test_assistant_sans_modele_renvoie_les_passages_du_cgi(client, monkeypatch):
    monkeypatch.setattr(llm, "_appeler_groq", lambda *a, **k: None)
    d = client.post("/assistant/sit", json={"question": "réclamations présentées dans les six mois"}).json()
    assert d["genere"] is False and "pas disponible" in d["reponse"]
    assert d["sources"], "les passages du CGI restent utiles même sans le modèle de langage"


def test_assistant_valide_la_question(client):
    assert client.post("/assistant/sit", json={"question": ""}).status_code == 422
    assert client.post("/assistant/sit", json={"question": "x" * 501}).status_code == 422
