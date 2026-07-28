"""
GEIF - Détection d'anomalies sur les montants extraits
==========================================================
Approche statistique simple (z-score) par type de document et par champ
monétaire. Suffisant pour un POC et facilement interprétable pour un jury
(contrairement à une boîte noire) — un point important à mettre en avant
dans ton rapport.
"""
import json
from pathlib import Path

import numpy as np

MONEY_FIELDS = [
    "chiffre_affaires_ht", "montant_tva_du", "montant_is_du",
    "montant_rappel", "montant_conteste", "montant",
]


def compute_reference_stats(manifest_path: str) -> dict:
    """Calcule moyenne/écart-type par (type_document, champ) sur le dataset
    d'entraînement, pour servir de référence à la détection d'anomalies."""
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    stats = {}
    by_type = {}
    for rec in manifest:
        by_type.setdefault(rec["type_document"], []).append(rec)

    for doc_type, records in by_type.items():
        stats[doc_type] = {}
        for field in MONEY_FIELDS:
            values = [r[field] for r in records if field in r and not r.get("_is_anomaly")]
            if len(values) >= 3:
                stats[doc_type][field] = {
                    "mean": float(np.mean(values)),
                    "std": float(np.std(values)) or 1.0,
                }
    return stats


def flag_anomalies(doc_type: str, extracted_fields: dict, ref_stats: dict, z_threshold=2.5):
    """Retourne la liste des champs jugés anormaux (z-score au-delà du seuil)."""
    flags = []
    type_stats = ref_stats.get(doc_type, {})
    for field, value in extracted_fields.items():
        if field in MONEY_FIELDS and field in type_stats and isinstance(value, (int, float)):
            mean, std = type_stats[field]["mean"], type_stats[field]["std"]
            z = abs(value - mean) / std
            if z > z_threshold:
                flags.append({
                    "field": field,
                    "value": value,
                    "expected_mean": round(mean, 2),
                    "z_score": round(z, 2),
                })
    return flags


if __name__ == "__main__":
    stats = compute_reference_stats("../data/synthetic_dataset/manifest.json")
    print(json.dumps(stats, indent=2))
