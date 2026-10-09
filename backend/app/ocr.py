"""
OCR local (Tesseract) pour les documents scannés déposés sur le portail SIT.

- Images (PNG/JPG/JPEG) : OCR direct.
- PDF : rasterisé page par page avec PyMuPDF (fitz) — pas besoin de Poppler,
  seul Tesseract doit être installé sur la machine.

Si Tesseract n'est pas installé ou introuvable, on ne plante jamais le reste
de l'application : on renvoie un texte explicite, et le rapport/décision
utilisera alors uniquement les champs saisis dans le formulaire.
"""
import io

import pytesseract
from PIL import Image

from .config import settings

if settings.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

MAX_PAGES_PDF = 5  # on ne lit pas des PDF de 200 pages pour une pièce justificative


def _ocr_image(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang=settings.OCR_LANGS)


def verifier_ocr() -> dict:
    """Diagnostic — testé à chaud (pas seulement au démarrage) et exposé sur
    /health pour que le frontend affiche un statut clair au lieu de laisser
    l'OCR échouer silencieusement dossier après dossier."""
    try:
        version = str(pytesseract.get_tesseract_version())
    except pytesseract.pytesseract.TesseractNotFoundError:
        return {"ok": False, "message": "Tesseract introuvable — installe-le ou renseigne TESSERACT_CMD dans backend/.env."}
    except Exception as e:
        return {"ok": False, "message": f"Tesseract inaccessible : {e}"}

    try:
        import pytesseract as _p
        langues = set(_p.get_languages(config=""))
    except Exception:
        langues = set()

    manquantes = [l for l in settings.OCR_LANGS.split("+") if l not in langues]
    if manquantes:
        return {
            "ok": False,
            "message": f"Tesseract {version} trouvé mais fichier(s) de langue manquant(s) : {', '.join(manquantes)} "
                       f"— télécharge-les depuis github.com/tesseract-ocr/tessdata et place-les dans le dossier tessdata.",
        }
    return {"ok": True, "message": f"Tesseract {version} — langues {', '.join(sorted(langues))}"}


def extraire_texte_document(contenu: bytes, content_type: str, nom_fichier: str) -> str:
    """Retourne le texte OCR du document, ou un message explicite en cas
    d'échec — jamais une exception qui remonterait jusqu'à l'utilisateur."""
    try:
        if content_type in ("image/png", "image/jpeg"):
            img = Image.open(io.BytesIO(contenu))
            texte = _ocr_image(img)
            return texte.strip() or "(OCR : aucun texte détecté sur l'image)"

        if content_type == "application/pdf":
            import fitz  # PyMuPDF — import local pour ne pas ralentir le démarrage
            doc = fitz.open(stream=contenu, filetype="pdf")
            morceaux = []
            for i, page in enumerate(doc):
                if i >= MAX_PAGES_PDF:
                    morceaux.append(f"[... document tronqué après {MAX_PAGES_PDF} pages ...]")
                    break
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                morceaux.append(_ocr_image(img))
            doc.close()
            texte = "\n".join(m.strip() for m in morceaux if m.strip())
            return texte or "(OCR : aucun texte détecté dans le PDF)"

        return f"(Type de fichier non pris en charge par l'OCR : {content_type})"

    except pytesseract.pytesseract.TesseractNotFoundError:
        return (
            "(OCR indisponible : Tesseract n'est pas installé ou TESSERACT_CMD "
            "n'est pas configuré dans backend/.env — voir le README.)"
        )
    except Exception as e:
        return f"(Échec de l'OCR sur « {nom_fichier} » : {e})"
