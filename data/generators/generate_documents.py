"""
GEIF - Générateur de documents fiscaux synthétiques
=====================================================
Génère un jeu de données d'entraînement/test réaliste SANS utiliser de
données réelles confidentielles de la DGI. Chaque document est une image
(simulant un scan) contenant du texte structuré selon le type de document.

Types générés :
  - declaration_tva
  - declaration_is
  - avis_redressement
  - reclamation
  - justificatif

Usage :
    python generate_synthetic_data.py --n 200 --out ./synthetic_dataset
"""
import argparse
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

random.seed(42)

DOC_TYPES = [
    "declaration_tva",
    "declaration_is",
    "avis_redressement",
    "reclamation",
    "justificatif",
]

VILLES = ["Rabat", "Casablanca", "Fès", "Marrakech", "Tanger", "Agadir", "Oujda"]
SOCIETES = ["ATLAS SARL", "MAGHREB TRADE SA", "NORD INDUSTRIE", "OCEANE SERVICES",
            "MEDINA CONSULTING", "RIF DISTRIBUTION", "SAHARA TECH"]
MOTIFS_REDRESSEMENT = [
    "Insuffisance de déclaration de chiffre d'affaires",
    "Charges non justifiées",
    "Anomalie sur les amortissements déclarés",
    "Discordance entre CA déclaré et recoupements bancaires",
]
MOTIFS_RECLAMATION = [
    "Contestation du montant de la taxe professionnelle",
    "Demande de dégrèvement pour erreur matérielle",
    "Contestation d'un avis de redressement",
    "Demande de délai de paiement",
]


def rand_date(start_year=2024, end_year=2026):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def rand_ice():
    return "".join(str(random.randint(0, 9)) for _ in range(15))


def rand_if():
    return str(random.randint(10000000, 99999999))


def gen_fields(doc_type):
    date = rand_date()
    societe = random.choice(SOCIETES)
    ville = random.choice(VILLES)
    fields = {
        "type_document": doc_type,
        "date": date.strftime("%d/%m/%Y"),
        "ville": ville,
        "identifiant_fiscal": rand_if(),
        "ice": rand_ice(),
        "raison_sociale": societe,
    }

    if doc_type == "declaration_tva":
        ca_ht = round(random.uniform(20000, 800000), 2)
        tva = round(ca_ht * 0.20, 2)
        fields.update({
            "periode": f"{random.choice(['Janvier','Février','Mars','Avril','Mai','Juin'])} {date.year}",
            "chiffre_affaires_ht": ca_ht,
            "montant_tva_du": tva,
        })

    elif doc_type == "declaration_is":
        resultat = round(random.uniform(-50000, 900000), 2)
        is_du = round(max(resultat, 0) * 0.31, 2)
        fields.update({
            "exercice": str(date.year - 1),
            "resultat_fiscal": resultat,
            "montant_is_du": is_du,
        })

    elif doc_type == "avis_redressement":
        montant_rappel = round(random.uniform(5000, 300000), 2)
        fields.update({
            "reference_dossier": f"RED-{date.year}-{random.randint(1000,9999)}",
            "motif": random.choice(MOTIFS_REDRESSEMENT),
            "montant_rappel": montant_rappel,
            "delai_reponse_jours": random.choice([30, 60]),
        })

    elif doc_type == "reclamation":
        montant_conteste = round(random.uniform(2000, 150000), 2)
        fields.update({
            "reference_imposition": f"IMP-{date.year}-{random.randint(1000,9999)}",
            "objet": random.choice(MOTIFS_RECLAMATION),
            "montant_conteste": montant_conteste,
        })

    elif doc_type == "justificatif":
        montant = round(random.uniform(500, 50000), 2)
        fields.update({
            "nature": random.choice(["Facture", "Quittance", "Acte notarié"]),
            "montant": montant,
            "partie_prenante": random.choice(SOCIETES),
        })

    # Inject occasional anomalies for the anomaly-detection module downstream
    is_anomaly = random.random() < 0.08
    if is_anomaly:
        if "montant_tva_du" in fields:
            fields["montant_tva_du"] *= random.choice([0.1, 5])
        elif "montant_is_du" in fields:
            fields["montant_is_du"] *= random.choice([0.1, 6])
        elif "montant_rappel" in fields:
            fields["montant_rappel"] *= 8
    fields["_is_anomaly"] = is_anomaly

    return fields


def render_document(fields, path, font_path=None):
    """Render fields as a scanned-looking document image."""
    W, H = 900, 1200
    img = Image.new("RGB", (W, H), color=(250, 248, 242))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype(font_path or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        body_font = ImageFont.truetype(font_path or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        small_font = ImageFont.truetype(font_path or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        title_font = body_font = small_font = ImageFont.load_default()

    # Header
    draw.rectangle([(30, 30), (W - 30, 110)], outline=(20, 60, 40), width=2)
    draw.text((45, 45), "ROYAUME DU MAROC", font=body_font, fill=(20, 60, 40))
    draw.text((45, 70), "DIRECTION GENERALE DES IMPOTS", font=title_font, fill=(20, 60, 40))

    y = 140
    title_map = {
        "declaration_tva": "DECLARATION DE LA TAXE SUR LA VALEUR AJOUTEE",
        "declaration_is": "DECLARATION DE L'IMPOT SUR LES SOCIETES",
        "avis_redressement": "AVIS DE REDRESSEMENT",
        "reclamation": "RECLAMATION FISCALE",
        "justificatif": "PIECE JUSTIFICATIVE",
    }
    draw.text((45, y), title_map[fields["type_document"]], font=title_font, fill=(60, 20, 20))
    y += 45

    draw.line([(45, y), (W - 45, y)], fill=(180, 170, 140), width=1)
    y += 20

    skip_keys = {"type_document", "_is_anomaly"}
    for key, val in fields.items():
        if key in skip_keys:
            continue
        label = key.replace("_", " ").capitalize()
        draw.text((45, y), f"{label} :", font=body_font, fill=(40, 40, 30))
        draw.text((320, y), str(val), font=body_font, fill=(10, 10, 10))
        y += 32

    draw.text((45, H - 60), f"Document généré à des fins de test — {datetime.now().year}",
               font=small_font, fill=(150, 150, 150))

    img.save(path)


def build_dataset(n, out_dir):
    out_dir = Path(out_dir)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    manifest = []

    for i in range(n):
        doc_type = random.choice(DOC_TYPES)
        fields = gen_fields(doc_type)
        filename = f"doc_{i:04d}_{doc_type}.png"
        render_document(fields, out_dir / "images" / filename)
        record = {"filename": filename, **fields}
        manifest.append(record)

    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

    print(f"✅ {n} documents générés dans {out_dir}/images/")
    print(f"✅ manifest.json créé ({len(manifest)} entrées)")
    n_anom = sum(1 for m in manifest if m["_is_anomaly"])
    print(f"   dont {n_anom} anomalies injectées ({n_anom/n*100:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200, help="Nombre de documents à générer")
    parser.add_argument("--out", type=str, default="./synthetic_dataset", help="Dossier de sortie")
    args = parser.parse_args()
    build_dataset(args.n, args.out)
