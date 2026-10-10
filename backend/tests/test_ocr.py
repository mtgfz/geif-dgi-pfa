"""OCR : réparation automatique quand Tesseract ne peut pas ouvrir les langues (bug Windows réel)."""
import glob
import io
import os
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

import app.ocr as ocr
from app.config import settings

pytesseract = pytest.importorskip("pytesseract")
TESSERACT = shutil.which("tesseract")
pytestmark = pytest.mark.skipif(TESSERACT is None, reason="Tesseract non installé sur cette machine")

ERREUR_WINDOWS = ("Error opening data file C:\\Program Files\\Tesseract-OCR/tessdata/fra.traineddata "
                  "Please make sure the TESSDATA_PREFIX environment variable is set to your \"tessdata\" directory. "
                  "Failed loading language 'fra' Tesseract couldn't load any languages! Could not initialize tesseract.")


def _png():
    img = Image.new("RGB", (1100, 140), "white")
    ImageDraw.Draw(img).text((20, 40), "Identifiant fiscal : 12345601", fill="black", font=ImageFont.load_default(size=34))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def installation_windows_cassee(tmp_path, monkeypatch):
    """Simule : le dossier par défaut de Tesseract ne s'ouvre pas, mais <dossier de tesseract.exe>/tessdata fonctionne."""
    install = tmp_path / "Tesseract-OCR"
    (install / "tessdata").mkdir(parents=True)
    os.symlink(TESSERACT, install / "tesseract")
    source = glob.glob("/usr/share/tesseract-ocr/*/tessdata/fra.traineddata")[0]
    shutil.copy(source, install / "tessdata" / "fra.traineddata")

    monkeypatch.setattr(settings, "TESSERACT_CMD", str(install / "tesseract"))
    monkeypatch.setattr(settings, "TESSDATA_LOCAL", str(tmp_path / "inexistant"))
    monkeypatch.setattr(settings, "OCR_LANGS", "fra+ara")
    original = pytesseract.image_to_string

    def faux(image, lang=None, config="", **kw):
        if "--tessdata-dir" not in config:
            raise pytesseract.TesseractError(1, ERREUR_WINDOWS)
        return original(image, lang=lang, config=config, **kw)

    monkeypatch.setattr(pytesseract, "image_to_string", faux)
    monkeypatch.setattr(ocr, "_etat", None)
    yield install
    ocr._etat = None


def test_repare_en_utilisant_le_dossier_tessdata_voisin(installation_windows_cassee):
    etat = ocr.initialiser(force=True)
    assert etat["ok"], etat["message"]
    assert etat["langues_utilisees"] == ["fra"] and etat["langues_manquantes"] == ["ara"]
    assert etat["tessdata_dir"] == str(installation_windows_cassee / "tessdata")
    # le chemin Windows est passé en « / » et entre guillemets (shlex détruit les « \ »)
    assert etat["tessdata_config"].startswith('--tessdata-dir "') and "\\" not in etat["tessdata_config"]
    r = ocr.extraire_document(_png(), "image/png", "scan.png")
    assert r["ok"] and r["champs"]["identifiant_fiscal"] == "12345601", r


def test_echec_total_donne_un_diagnostic_actionnable(installation_windows_cassee, monkeypatch):
    def toujours_ko(*a, **k):
        raise pytesseract.TesseractError(1, ERREUR_WINDOWS)
    monkeypatch.setattr(pytesseract, "image_to_string", toujours_ko)
    monkeypatch.setenv("TESSDATA_PREFIX", "C:\\mauvais\\endroit")
    etat = ocr.initialiser(force=True)
    assert etat["ok"] is False
    assert "Error opening data file" in etat["message"]
    assert any("backend" in c and "tessdata" in c for c in etat["conseils"])
    assert any("TESSDATA_PREFIX" in c for c in etat["conseils"])
    r = ocr.extraire_document(_png(), "image/png", "scan.png")
    assert r["ok"] is False and r["texte"] == "" and "OCR impossible" in r["erreur"]  # jamais d'erreur cachée dans le texte
