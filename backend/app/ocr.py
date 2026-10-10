"""
OCR local (Tesseract) pour les documents déposés sur le portail SIT.

  - Images (PNG/JPG) : OCR direct.
  - PDF : PyMuPDF (fitz) — pas besoin de Poppler. Un PDF numérique (avec
    couche texte) est lu directement ; un scan est rasterisé puis passé à
    Tesseract. OCR_FORCER=1 force Tesseract partout.

Robustesse (le point faible de la version précédente) :
  - Tesseract est cherché automatiquement : TESSERACT_CMD, PATH, puis les
    dossiers d'installation Windows habituels.
  - Si une langue demandée manque (ex : « ara »), on utilise celles qui sont
    disponibles au lieu d'échouer. On peut aussi déposer les .traineddata
    dans backend/tessdata/ (aucun droit administrateur nécessaire).
  - Une erreur d'OCR n'est JAMAIS cachée dans le texte : elle est renvoyée
    à part (champ « erreur »), et le texte reste vide.

Diagnostic complet :   cd backend && python -m app.ocr
OCR d'un fichier   :   cd backend && python -m app.ocr chemin/vers/fichier.pdf
"""
import io
import os
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

from .config import settings

try:
    import pytesseract
except ImportError:  # l'application doit démarrer même sans pytesseract
    pytesseract = None

MAX_PAGES_PDF = 5          # on ne lit pas 200 pages pour une pièce justificative
SEUIL_TEXTE_PDF = 40       # caractères minimum pour considérer qu'une page PDF a une couche texte

_CHEMINS_WINDOWS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
    os.path.join(os.environ.get("USERPROFILE", ""), "scoop", "apps", "tesseract", "current", "tesseract.exe"),
]

_etat: dict | None = None  # cache de l'initialisation


# ---------------------------------------------------------------------
# Détection de Tesseract et des langues
# ---------------------------------------------------------------------
def _nettoyer(chemin: str) -> str:
    return (chemin or "").strip().strip('"').strip("'").strip()


def trouver_tesseract() -> str | None:
    candidat = _nettoyer(settings.TESSERACT_CMD)
    if candidat and Path(candidat).is_file():
        return candidat
    trouve = shutil.which("tesseract")
    if trouve:
        return trouve
    for chemin in _CHEMINS_WINDOWS:
        if chemin and Path(chemin).is_file():
            return chemin
    return None


def _langues_dossier(dossier: Path) -> set:
    try:
        return {f.stem for f in dossier.glob("*.traineddata")}
    except OSError:
        return set()


def _dossier_local() -> Path | None:
    d = Path(settings.TESSDATA_LOCAL).resolve()
    return d if d.is_dir() and _langues_dossier(d) else None


def _config_tessdata(dossier: Path | None) -> str:
    # as_posix() : pytesseract découpe la config avec shlex, qui détruit les « \ » Windows
    return f'--tessdata-dir "{dossier.as_posix()}"' if dossier else ""


def _sonde(dossier: "Path | None", langues: str) -> str | None:
    """Fait VRAIMENT tourner Tesseract sur une image vierge. Retourne None si OK,
    sinon le message d'erreur (ex : « Error opening data file ... fra.traineddata »).
    Lister les langues ne suffit pas : on a vu des installations qui listent « fra »
    mais ne parviennent pas à l'ouvrir."""
    try:
        pytesseract.image_to_string(Image.new("L", (160, 60), 255), lang=langues, config=_config_tessdata(dossier))
        return None
    except Exception as e:  # noqa: BLE001
        return " ".join(str(e).split())[:400]


def _candidats_tessdata() -> list:
    """Dossiers tessdata à essayer, par ordre de préférence. None = réglage par défaut de Tesseract."""
    candidats = []
    local = _dossier_local()
    if local:
        candidats.append(local)
    if etat_cmd := _etat_cmd():
        voisin = Path(etat_cmd).parent / "tessdata"
        if voisin.is_dir():
            candidats.append(voisin)
    prefixe = _nettoyer(os.environ.get("TESSDATA_PREFIX", ""))
    if prefixe:
        for p in (Path(prefixe), Path(prefixe) / "tessdata"):
            if p.is_dir() and _langues_dossier(p):
                candidats.append(p)
    uniques = []
    for c in candidats:
        if c.resolve() not in [u.resolve() for u in uniques if u]:
            uniques.append(c)
    uniques.append(None)  # défaut de Tesseract, en dernier
    return uniques


def _etat_cmd() -> str | None:
    return getattr(pytesseract.pytesseract, "tesseract_cmd", None) if pytesseract else None


def initialiser(force: bool = False) -> dict:
    """Détecte Tesseract et choisit une configuration (dossier tessdata + langues) qui MARCHE
    réellement, en testant chaque option. Résultat mis en cache."""
    global _etat
    if _etat is not None and not force:
        return _etat

    etat = {
        "ok": False, "message": "", "conseils": [], "version": None, "cmd": None,
        "langues_demandees": [l for l in settings.OCR_LANGS.split("+") if l],
        "langues_disponibles": [], "langues_utilisees": [], "langues_manquantes": [],
        "tessdata_dir": None, "tessdata_config": "", "tessdata_prefix_env": os.environ.get("TESSDATA_PREFIX") or None,
        "essais": [], "pytesseract": pytesseract is not None, "pymupdf": False,
    }
    try:
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            import fitz  # noqa: F401
        etat["pymupdf"] = True
    except ImportError:
        etat["conseils"].append("PyMuPDF absent : les PDF ne seront pas lus → pip install pymupdf")

    if pytesseract is None:
        etat["message"] = "Le module Python pytesseract n'est pas installé."
        etat["conseils"].append("pip install pytesseract pillow pymupdf")
        _etat = etat
        return etat

    cmd = trouver_tesseract()
    if not cmd:
        etat["message"] = "Tesseract est introuvable sur cette machine."
        etat["conseils"] += [
            "Windows : installe Tesseract (https://github.com/UB-Mannheim/tesseract/wiki), "
            "en cochant « French » et « Arabic » dans Additional language data.",
            "Puis renseigne dans backend/.env :  TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
            "Linux/Docker : apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara",
        ]
        _etat = etat
        return etat

    pytesseract.pytesseract.tesseract_cmd = cmd
    etat["cmd"] = cmd
    try:
        etat["version"] = str(pytesseract.get_tesseract_version())
    except Exception as e:
        etat["message"] = f"Tesseract trouvé ({cmd}) mais impossible de l'exécuter : {e}"
        etat["conseils"].append("Vérifie que le chemin pointe vers tesseract.exe et que l'installation n'est pas corrompue.")
        _etat = etat
        return etat

    demandees = etat["langues_demandees"]
    etat["langues_disponibles"] = set()

    # On essaie chaque dossier tessdata ; pour chacun : toutes les langues demandées,
    # puis chaque langue seule. Le premier qui fonctionne VRAIMENT gagne.
    gagnant = None
    for dossier in _candidats_tessdata():
        if dossier is None:
            try:
                dispo = set(pytesseract.get_languages(config=""))
            except Exception:
                dispo = set()
            nom = "réglage par défaut de Tesseract"
        else:
            dispo = _langues_dossier(dossier)
            nom = str(dossier)
        etat["langues_disponibles"] |= dispo
        utilisables = [l for l in demandees if l in dispo]
        secours = [l for l in ("fra", "eng") if l in dispo and l not in utilisables]
        essais = []
        if utilisables:
            essais.append("+".join(utilisables))
            essais += [l for l in utilisables if len(utilisables) > 1]
        essais += secours
        vus = set()
        for langues in [e for e in essais if not (e in vus or vus.add(e))]:
            erreur = _sonde(dossier, langues)
            etat["essais"].append({"dossier": nom, "langues": langues, "ok": erreur is None, "erreur": erreur})
            if erreur is None:
                gagnant = (dossier, langues.split("+"), dispo)
                break
        if gagnant:
            break

    etat["langues_disponibles"] = sorted(etat["langues_disponibles"])
    if not gagnant:
        derniere = next((e["erreur"] for e in reversed(etat["essais"]) if e["erreur"]), "aucun fichier de langue trouvé")
        etat["message"] = f"Tesseract {etat['version']} est installé mais ne parvient à charger aucune langue. Dernière erreur : {derniere}"
        etat["conseils"] += [
            "Télécharge fra.traineddata (et ara.traineddata) : https://github.com/tesseract-ocr/tessdata_fast",
            "Place-les dans le dossier  backend\\tessdata\\  (à créer s'il n'existe pas), puis relance :  python -m app.ocr",
        ]
        if etat["tessdata_prefix_env"]:
            etat["conseils"].append(
                f"La variable d'environnement TESSDATA_PREFIX est définie ({etat['tessdata_prefix_env']}) : "
                "supprime-la ou corrige-la (elle doit pointer vers le dossier « tessdata »)."
            )
        _etat = etat
        return etat

    dossier, utilisees, dispo = gagnant
    etat["ok"] = True
    etat["langues_utilisees"] = utilisees
    etat["langues_manquantes"] = [l for l in demandees if l not in utilisees]
    etat["tessdata_dir"] = str(dossier) if dossier else None
    etat["tessdata_config"] = _config_tessdata(dossier)
    etat["message"] = f"Tesseract {etat['version']} actif — langues utilisées : {'+'.join(utilisees)}"
    if dossier:
        etat["message"] += f" (dossier : {dossier})"
    if etat["langues_manquantes"]:
        etat["message"] += f" — non utilisables : {', '.join(etat['langues_manquantes'])}"
        etat["conseils"].append(
            f"Pour lire aussi {', '.join(etat['langues_manquantes'])} : place le(s) fichier(s) .traineddata dans backend/tessdata/ "
            "(https://github.com/tesseract-ocr/tessdata_fast)."
        )
    if "fra" not in utilisees and "fra" in demandees:
        etat["conseils"].append("Le français (fra) n'est pas utilisable : l'OCR des documents français sera dégradé.")
    _etat = etat
    return etat


def verifier_ocr(force: bool = False) -> dict:
    """Résumé pour /health et l'interface (mis en cache : le test réel lance Tesseract)."""
    e = initialiser(force=force)
    return {
        "ok": e["ok"], "message": e["message"], "conseils": e["conseils"],
        "langues_utilisees": e["langues_utilisees"], "langues_manquantes": e["langues_manquantes"],
        "pymupdf": e["pymupdf"],
    }


# ---------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------
def _preparer(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img)
    if img.width < 1200:  # les petites images sont mal lues : on agrandit
        facteur = 1200 / img.width
        img = img.resize((int(img.width * facteur), int(img.height * facteur)), Image.LANCZOS)
    return img


def _ocr_image(img: Image.Image) -> str:
    etat = initialiser()
    if not etat["ok"]:
        raise RuntimeError(etat["message"])
    img = _preparer(img)
    langues = "+".join(etat["langues_utilisees"])
    try:
        return pytesseract.image_to_string(img, lang=langues, config=etat["tessdata_config"])
    except pytesseract.TesseractError:
        # Dernier recours : une seule langue (la première utilisable)
        return pytesseract.image_to_string(img, lang=etat["langues_utilisees"][0], config=etat["tessdata_config"])


def extraire_document(contenu: bytes, content_type: str, nom_fichier: str) -> dict:
    """
    Lit un document. Ne lève jamais d'exception.
    Retourne {texte, ok, methode, erreur, champs}.
      methode : "ocr" | "texte_pdf" | "mixte" | "aucune"
    """
    resultat = {"texte": "", "ok": False, "methode": "aucune", "erreur": None, "champs": {}}
    try:
        if content_type in ("image/png", "image/jpeg"):
            texte = _ocr_image(Image.open(io.BytesIO(contenu))).strip()
            resultat.update(texte=texte, methode="ocr", ok=bool(texte))
            if not texte:
                resultat["erreur"] = "Aucun texte détecté sur l'image (image trop floue ou vide ?)."

        elif content_type == "application/pdf":
            try:
                try:
                    import pymupdf as fitz  # PyMuPDF (nom récent)
                except ImportError:
                    import fitz  # ancien nom
            except ImportError:
                raise RuntimeError("PyMuPDF n'est pas installé (pip install pymupdf).")
            doc = fitz.open(stream=contenu, filetype="pdf")
            morceaux, methodes = [], set()
            for i, page in enumerate(doc):
                if i >= MAX_PAGES_PDF:
                    morceaux.append(f"[... document tronqué après {MAX_PAGES_PDF} pages ...]")
                    break
                couche = page.get_text().strip()
                if len(couche) >= SEUIL_TEXTE_PDF and not settings.OCR_FORCER:
                    morceaux.append(couche)
                    methodes.add("texte_pdf")
                else:
                    pix = page.get_pixmap(dpi=250)
                    morceaux.append(_ocr_image(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)).strip())
                    methodes.add("ocr")
            doc.close()
            texte = "\n".join(m for m in morceaux if m)
            resultat.update(texte=texte, ok=bool(texte),
                            methode="mixte" if len(methodes) > 1 else (next(iter(methodes)) if methodes else "aucune"))
            if not texte:
                resultat["erreur"] = "Aucun texte détecté dans le PDF."
        else:
            resultat["erreur"] = f"Type de fichier non pris en charge : {content_type}"
    except Exception as e:  # noqa: BLE001 — jamais d'exception vers l'utilisateur
        resultat["erreur"] = f"OCR impossible sur « {nom_fichier} » : {e}"

    if resultat["texte"]:
        resultat["champs"] = extraire_champs(resultat["texte"])
    return resultat


# ---------------------------------------------------------------------
# Extraction de champs (affichés au gestionnaire dans la page Traiter)
# ---------------------------------------------------------------------
def _nombre(brut: str) -> float | None:
    """Convertit « 1.234.567,50 », « 184 500,00 », « 1,234,567.50 » ou « 1.234 » en nombre."""
    s = re.sub(r"[\s\u00a0]", "", brut)
    if "," in s and "." in s:
        # le dernier séparateur est la virgule décimale ; l'autre sépare les milliers
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif "." in s:
        apres = s.rsplit(".", 1)[1]
        if s.count(".") > 1 or len(apres) == 3:  # 1.234.567 ou 1.234 -> milliers
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def extraire_champs(texte: str) -> dict:
    """Champs repérables par motifs (IF, ICE, montants, dates, références, articles).
    Volontairement prudent : un champ non trouvé est simplement absent."""
    t = texte.replace("\u00a0", " ")
    champs: dict = {}

    m = re.search(r"(?:identifiant\s+fiscal|\bI\.?F\.?)\s*(?:n°|no|num[ée]ro)?\s*[:\-]?\s*(\d{6,10})\b", t, re.I)
    if m:
        champs["identifiant_fiscal"] = m.group(1)
    m = re.search(r"\bICE\b\s*(?:n°|no)?\s*[:\-]?\s*(\d{15})\b", t, re.I)
    if m:
        champs["ice"] = m.group(1)
    m = re.search(r"(?:registre\s+de\s+commerce|\bR\.?C\.?)\s*(?:n°|no)?\s*[:\-]?\s*(\d{3,10})\b", t, re.I)
    if m:
        champs["registre_commerce"] = m.group(1)

    montants = []
    for brut in re.findall(r"(\d[\d\s.,]*\d|\d)\s*(?:MAD|DHS?|dirhams?)\b", t, re.I):
        v = _nombre(brut)
        if v is not None and v not in montants:
            montants.append(v)
    if montants:
        champs["montants"] = montants[:8]

    dates = []
    for d in re.findall(r"\b(\d{2}[/.\-]\d{2}[/.\-]\d{4})\b", t):
        if d not in dates:
            dates.append(d)
    if dates:
        champs["dates"] = dates[:6]

    m = re.search(r"(?:r[ée]f(?:[ée]rence)?\.?|dossier)\s*(?:n°|no)?\s*[:\-]\s*([A-Z0-9][A-Z0-9/\-]{3,})", t, re.I)
    if m:
        champs["reference"] = m.group(1)

    arts = []
    for a in re.findall(r"\bart(?:icle|\.)?\s*(\d{1,3}(?:\s*(?:bis|ter))?)", t, re.I):
        a = a.strip()
        if a not in arts:
            arts.append(a)
    if arts:
        champs["articles_cites"] = arts[:8]
    return champs


# ---------------------------------------------------------------------
# Diagnostic en ligne de commande
# ---------------------------------------------------------------------
def _autotest() -> str:
    from PIL import ImageDraw, ImageFont
    img = Image.new("RGB", (1000, 220), "white")
    d = ImageDraw.Draw(img)
    try:
        police = ImageFont.load_default(size=36)
    except TypeError:
        police = ImageFont.load_default()
    d.text((20, 30), "Identifiant fiscal : 12345678", fill="black", font=police)
    d.text((20, 110), "Montant conteste : 184 500,00 DH", fill="black", font=police)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    r = extraire_document(buf.getvalue(), "image/png", "autotest.png")
    return r["texte"] if r["ok"] else f"ÉCHEC : {r['erreur']}"


if __name__ == "__main__":
    e = initialiser(force=True)
    print("=" * 60)
    print("DIAGNOSTIC OCR GEIF")
    print("=" * 60)
    print("pytesseract  :", "OK" if e["pytesseract"] else "ABSENT")
    print("PyMuPDF      :", "OK" if e["pymupdf"] else "ABSENT")
    print("Exécutable   :", e["cmd"] or "INTROUVABLE")
    print("Version      :", e["version"])
    print("Langues dispo:", ", ".join(e["langues_disponibles"]) or "-")
    print("Langues demandées/utilisées/manquantes :",
          "+".join(e["langues_demandees"]), "/", "+".join(e["langues_utilisees"]) or "-", "/",
          ",".join(e["langues_manquantes"]) or "-")
    print("Dossier tessdata choisi:", e["tessdata_dir"] or "(défaut de Tesseract)")
    print("TESSDATA_PREFIX (env)  :", e["tessdata_prefix_env"] or "(non défini)")
    print("Essais effectués :")
    for t in e["essais"]:
        print("   ", "OK " if t["ok"] else "KO ", t["langues"], "@", t["dossier"], "" if t["ok"] else "→ " + t["erreur"][:160])
    print("-" * 60)
    print("RÉSULTAT :", "✅" if e["ok"] else "❌", e["message"])
    for c in e["conseils"]:
        print("  →", c)
    if e["ok"]:
        print("-" * 60)
        if len(sys.argv) > 1:
            chemin = Path(sys.argv[1])
            ct = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(chemin.suffix.lower(), "")
            r = extraire_document(chemin.read_bytes(), ct, chemin.name)
            print(f"Méthode : {r['methode']}   OK : {r['ok']}   Erreur : {r['erreur']}")
            print("Champs :", r["champs"])
            print("Texte :\n", r["texte"][:1500])
        else:
            print("Auto-test (image générée) →", _autotest())
    sys.exit(0 if e["ok"] else 1)
