"""Fixtures de test : MongoDB simulé (mongomock), RAG simulé, aucune clé Groq, aucun SMTP."""
import os
import sys
from pathlib import Path

import mongomock
import pymongo
import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-0123456789abcdef")
os.environ["GROQ_API_KEY"] = ""
os.environ["RAG_PRECHAUFFER"] = "0"
os.environ["SMTP_HOST"] = ""
os.environ["CODE_CHEF_SERVICE"] = "CS-TEST"
os.environ["CODE_CHEF_SUBDIVISION"] = "CSUB-TEST"
os.environ["CODE_GESTIONNAIRE"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pymongo.MongoClient = mongomock.MongoClient  # avant l'import de app.database

from fastapi.testclient import TestClient  # noqa: E402

import app.rag as rag  # noqa: E402
from app import ratelimit  # noqa: E402
from app.database import db  # noqa: E402
from app.rules_engine import init_rules  # noqa: E402
from main import app  # noqa: E402


class _FauxVecteur:
    def tolist(self):
        return [[0.0]]


class _FauxModele:
    def encode(self, _):
        return _FauxVecteur()


class _FausseCollection:
    def query(self, query_embeddings, n_results):
        docs = [
            ("Article 235 - Les réclamations doivent être présentées dans les six mois.", {"article": "Art. 235 CGI", "page": 120}),
            ("Article 232 - Réparation des erreurs et omissions de liquidation.", {"article": "Art. 232 CGI", "page": 118}),
            ("Article 235 (suite) - délai six mois mise en recouvrement.", {"article": "Art. 235 CGI", "page": 121}),
            ("Article 10 - charges déductibles.", {"article": "Art. 10 CGI", "page": 12}),
        ]
        return {"documents": [[d for d, _ in docs]], "metadatas": [[m for _, m in docs]]}


@pytest.fixture(autouse=True)
def isolation_totale(monkeypatch):
    """Les tests ne doivent JAMAIS dépendre de ton vrai backend/.env (config.py le charge
    avec override) ni toucher le réseau : on force des valeurs de test et on interdit
    tout appel Groq / SMTP réel."""
    from app.config import settings
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "JWT_SECRET", "test-secret-key-0123456789abcdef")
    monkeypatch.setattr(settings, "ROLE_REGISTRATION_CODES", {
        "gestionnaire": "", "chef_service": "CS-TEST", "chef_subdivision": "CSUB-TEST",
    })

    def _interdit(*a, **k):
        raise AssertionError("Appel réseau interdit pendant les tests (Groq/SMTP).")
    import requests
    import smtplib
    monkeypatch.setattr(requests, "post", _interdit)
    monkeypatch.setattr(smtplib, "SMTP", _interdit)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _interdit)
    yield


@pytest.fixture(autouse=True)
def base_propre(monkeypatch):
    for nom in db.list_collection_names():
        db.drop_collection(nom)
    ratelimit.reinitialiser()
    init_rules()
    monkeypatch.setattr(rag, "_get_rag", lambda: (_FausseCollection(), _FauxModele()))
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _creer_et_connecter(client, username, role, code=None):
    r = client.post("/auth/signup", json={"username": username, "password": "motdepasse1", "role": role, "registration_code": code})
    assert r.status_code == 200, r.text
    r = client.post("/auth/login", json={"username": username, "password": "motdepasse1"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture()
def G(client):
    return _creer_et_connecter(client, "gest1", "gestionnaire")


@pytest.fixture()
def CS(client):
    return _creer_et_connecter(client, "chefserv1", "chef_service", "CS-TEST")


@pytest.fixture()
def CSUB(client):
    return _creer_et_connecter(client, "chefsub1", "chef_subdivision", "CSUB-TEST")


@pytest.fixture()
def depot(client):
    """Dépose une réclamation (portail public) et retourne (id, cle)."""
    def _depot(**over):
        corps = {
            "contrib": "Société Atlas SARL", "ifn": "12345601", "tax": "TVA",
            "motif": "TVA déductible non prise en compte", "montant": 100000,
            "date_mer": "2024-01-10", "date_reclam": "2024-03-01",
            "email": "contact@atlas.example", "telephone": "0537000000",
        }
        corps.update(over)
        r = client.post("/reclamations", json=corps)
        assert r.status_code == 200, r.text
        return r.json()["id"], r.json()["cle_verification"]
    return _depot
