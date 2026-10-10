"""E-mail : le bon mode de connexion selon le port (cause de « Connection unexpectedly closed »)."""
import smtplib

import pytest

from app import email_service
from app.config import settings


class _FauxServeur:
    instances = []

    def __init__(self, kind, host, port, timeout=None):
        self.kind, self.host, self.port, self.calls = kind, host, port, []
        _FauxServeur.instances.append(self)

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): self.calls.append("starttls")
    def login(self, u, p): self.calls.append(("login", u, p))
    def sendmail(self, *a): self.calls.append("sendmail")
    def close(self): pass


@pytest.fixture()
def smtp(monkeypatch):
    _FauxServeur.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", lambda h, p, timeout=None: _FauxServeur("SMTP", h, p, timeout))
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda h, p, timeout=None: _FauxServeur("SMTP_SSL", h, p, timeout))
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_USER", "moi@gmail.com")
    monkeypatch.setattr(settings, "SMTP_FROM", "moi@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "abcd efgh ijkl mnop")
    return _FauxServeur.instances


def test_port_587_utilise_starttls(smtp, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    assert email_service.envoyer_email_confirmation_depot("a@b.c", "X", "REC-2026-111111", "AAAA-BBBB") is True
    s = smtp[0]
    assert s.kind == "SMTP" and s.calls[0] == "starttls" and "sendmail" in s.calls


def test_port_465_utilise_ssl_sans_starttls(smtp, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PORT", 465)
    assert email_service.envoyer_email_confirmation_depot("a@b.c", "X", "REC-2026-111111", "AAAA-BBBB") is True
    s = smtp[0]
    assert s.kind == "SMTP_SSL" and "starttls" not in s.calls


def test_mot_de_passe_application_gmail_sans_espaces(smtp, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    email_service.envoyer_email_decision("a@b.c", "X", "REC-2026-111111", "AAAA-BBBB", "Décision", 100.0)
    login = next(c for c in smtp[0].calls if isinstance(c, tuple))
    assert login == ("login", "moi@gmail.com", "abcdefghijklmnop")


def test_erreur_422_est_loggee_en_clair(client, capsys):
    r = client.post("/reclamations", json={"contrib": "X", "tax": "XX"})
    assert r.status_code == 422
    sortie = capsys.readouterr().out
    assert "[422] POST /reclamations" in sortie and "ifn" in sortie


def test_422_message_lisible_meme_pour_un_ancien_client(client, depot):
    rid, _ = depot()
    # Ancien portail : envoie les fichiers SANS le code de suivi
    r = client.post(f"/reclamations/{rid}/documents", data={"description_demande": "x"},
                    files={"demande_degrevement": ("a.png", b"x", "image/png")})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "Ctrl+F5" in detail          # jamais « [object Object] »
    # validation classique : texte lisible + liste brute disponible pour les nouveaux clients
    r = client.post("/reclamations", json={"contrib": "X", "ifn": "123456", "tax": "TVA", "motif": "abc", "montant": -1,
                                           "date_mer": "2024-01-10", "date_reclam": "2024-03-01"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and "montant" in r.json()["detail"]
    assert isinstance(r.json()["errors"], list)
