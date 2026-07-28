"""
GEIF - Module OCR et extraction de champs
===========================================
Étape 1 du pipeline : transformer une image de document scanné en texte brut,
puis extraire les champs structurés (montants, dates, références) via regex.

Ce module est volontairement découplé de la classification : on extrait
d'abord tout ce qu'on peut lire, la classification décide ensuite du type.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

import pytesseract
from PIL import Image, ImageFilter, ImageOps


def preprocess_image(img: Image.Image) -> Image.Image:
    """Prétraitement simple pour améliorer la qualité OCR sur des scans bruités."""
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def extract_text(image_path: str, lang: str = "fra") -> str:
    """Lance Tesseract sur l'image et retourne le texte brut."""
    img = Image.open(image_path)
    img = preprocess_image(img)
    text = pytesseract.image_to_string(img, lang=lang)
    return text


# --- Regex patterns pour l'extraction de champs métier ---
PATTERNS = {
    "date": r"Date\s*:\s*(\d{2}/\d{2}/\d{4})",
    "identifiant_fiscal": r"Identifiant fiscal\s*:\s*(\d{6,10})",
    "ice": r"Ice\s*:\s*(\d{10,17})",
    "chiffre_affaires_ht": r"Chiffre affaires ht\s*:\s*([\d.]+)",
    "montant_tva_du": r"Montant tva du\s*:\s*([\d.]+)",
    "montant_is_du": r"Montant is du\s*:\s*([\d.]+)",
    "montant_rappel": r"Montant rappel\s*:\s*([\d.]+)",
    "montant_conteste": r"Montant conteste\s*:\s*([\d.]+)",
    "reference_dossier": r"Reference dossier\s*:\s*([A-Z0-9\-]+)",
    "reference_imposition": r"Reference imposition\s*:\s*([A-Z0-9\-]+)",
    "motif": r"Motif\s*:\s*(.+?)(?=\s{2,}[A-Z]|\s*Montant|\s*Delai|$)",
    "objet": r"Objet\s*:\s*(.+?)(?=\s{2,}[A-Z]|\s*Montant|$)",
    "nature": r"Nature\s*:\s*(\w+)",
}


@dataclass
class ExtractionResult:
    raw_text: str
    fields: dict = field(default_factory=dict)
    confidence_flags: dict = field(default_factory=dict)


def extract_fields(raw_text: str) -> ExtractionResult:
    """Applique les patterns regex sur le texte OCR pour retrouver les champs clés."""
    result = ExtractionResult(raw_text=raw_text)
    normalized = raw_text.replace("\n", " ")

    for field_name, pattern in PATTERNS.items():
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            value = match.group(1)
            # Numeric fields: try to cast to float
            if field_name.startswith("montant") or field_name == "chiffre_affaires_ht":
                try:
                    value = float(value)
                except ValueError:
                    pass
            result.fields[field_name] = value
            result.confidence_flags[field_name] = "ok"
        else:
            result.confidence_flags[field_name] = "missing"

    return result


def process_document(image_path: str) -> ExtractionResult:
    """Pipeline complet : image -> texte OCR -> champs structurés."""
    text = extract_text(image_path)
    return extract_fields(text)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "../data/synthetic_dataset/images/doc_0000_declaration_tva.png"
    result = process_document(path)
    print("--- TEXTE OCR BRUT ---")
    print(result.raw_text)
    print("\n--- CHAMPS EXTRAITS ---")
    for k, v in result.fields.items():
        print(f"  {k}: {v}")
    print("\n--- CHAMPS MANQUANTS ---")
    missing = [k for k, v in result.confidence_flags.items() if v == "missing"]
    print(f"  {missing}")
