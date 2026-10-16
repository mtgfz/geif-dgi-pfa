"""
Données AMMC / banques : états financiers des émetteurs bancaires collectés par le scraper (market_data/scraper).

Sources (CSV, versionnés dans le dépôt) :
  - ammc_filings.csv       : un état financier par émetteur et par exercice (liens vers la fiche et le PDF de l'AMMC)
  - parsed_financials.csv  : indicateurs extraits automatiquement des PDF (total actif, résultat net, PNB…)

Honnêteté sur la qualité : l'extraction automatique des PDF est PARTIELLE. Chaque ligne porte un statut :
  valide      -> actif = passif (contrôle comptable satisfait)
  partiel     -> certaines valeurs extraites, non recoupées : à vérifier dans le PDF
  non_extrait -> aucune valeur lue
Les unités ne sont pas toujours détectées : elles sont indiquées telles que lues, sinon « non déterminée ».
Ces données servent de repère sectoriel (page AMMC & banques, rapprochement dans les dossiers) ; elles ne
nourrissent PAS la décision sur les réclamations.
"""
import csv
import difflib
import os
import re
import unicodedata
from threading import Lock

from .config import settings

STATUTS = {
    "valide": "Validé (actif = passif)",
    "partiel": "Partiel — à vérifier",
    "non_extrait": "Non extrait",
    "erreur": "Erreur de lecture",
}
_STOP = {"sa", "sarl", "sas", "societe", "anonyme", "groupe", "group", "bank", "banque", "du", "de", "des", "la", "le", "et", "of", "the", "maroc"}

_cache = {"cle": None, "lignes": []}
_lock = Lock()


def _norm(texte: str) -> str:
    sans_accents = "".join(c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def _cle(texte: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(texte))


def _nombre(v):
    try:
        v = (v or "").strip()
        return float(v) if v and v.lower() != "nan" else None
    except ValueError:
        return None


def _unite(note: str):
    n = _norm(note)
    if "millions" in n:
        return "millions de MAD"
    if "milliers" in n:
        return "milliers de MAD"
    return None


def _lire_csv(nom: str) -> list[dict]:
    chemin = os.path.join(settings.MARCHE_DIR, nom)
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def charger() -> list[dict]:
    """Lignes fusionnées (une par émetteur et exercice), mises en cache tant que les fichiers ne changent pas."""
    chemins = [os.path.join(settings.MARCHE_DIR, n) for n in ("ammc_filings.csv", "parsed_financials.csv")]
    cle = tuple((c, os.path.getmtime(c) if os.path.exists(c) else 0) for c in chemins)
    with _lock:
        if _cache["cle"] == cle:
            return _cache["lignes"]
        extraits = {}
        for r in _lire_csv("parsed_financials.csv"):
            extraits[_cle(re.sub(r"\.pdf$", "", r.get("file", ""), flags=re.I))] = r
        lignes = []
        for f in _lire_csv("ammc_filings.csv"):
            e = extraits.get(_cle(f"{f['company']}{f['year']}"), {})
            valeurs = {
                "total_actif": _nombre(e.get("total_actif_current")), "total_actif_precedent": _nombre(e.get("total_actif_previous")),
                "resultat_net": _nombre(e.get("resultat_net_current")), "resultat_net_precedent": _nombre(e.get("resultat_net_previous")),
                "pnb": _nombre(e.get("produit_net_bancaire_current")), "pnb_precedent": _nombre(e.get("produit_net_bancaire_previous")),
            }
            if e.get("error"):
                statut = "erreur"
            elif (e.get("balance_check") or "").strip().upper() == "OK":
                statut = "valide"
            elif any(v is not None for v in valeurs.values()):
                statut = "partiel"
            else:
                statut = "non_extrait"
            lignes.append({
                "banque": f["company"], "annee": int(f["year"]), "detail_url": f.get("detail_url"), "pdf_url": f.get("pdf_url"),
                **valeurs, "unite": _unite(e.get("scale_note", "")), "statut": statut, "statut_libelle": STATUTS[statut],
            })
        lignes.sort(key=lambda l: (l["banque"].lower(), l["annee"]))
        _cache.update(cle=cle, lignes=lignes)
        return lignes


def rechercher(banque=None, annee=None, statut=None, q=None) -> dict:
    toutes = charger()
    if not toutes:
        return {"disponible": False, "message": "Aucune donnée AMMC trouvée (market_data/scraper/*.csv).", "lignes": []}
    mot = _norm(q) if q else ""
    lignes = [
        l for l in toutes
        if (not banque or l["banque"] == banque) and (not annee or l["annee"] == int(annee))
        and (not statut or l["statut"] == statut) and (not mot or mot in _norm(l["banque"]))
    ]
    return {
        "disponible": True,
        "banques": sorted({l["banque"] for l in toutes}), "annees": sorted({l["annee"] for l in toutes}, reverse=True),
        "statuts": STATUTS,
        "kpis": {
            "banques": len({l["banque"] for l in toutes}), "etats_financiers": len(toutes),
            "extraits": sum(1 for l in toutes if l["statut"] in ("valide", "partiel")),
            "valides": sum(1 for l in toutes if l["statut"] == "valide"),
        },
        "total_filtre": len(lignes), "lignes": lignes,
    }


# ---------------------------------------------------------------------------------------------------------------
# Rapprochement : la raison sociale d'un contribuable correspond-elle à un émetteur du référentiel ?
# ---------------------------------------------------------------------------------------------------------------
def _jetons(texte: str) -> set:
    return {t for t in _norm(texte).split() if len(t) >= 3 and t not in _STOP}


def rapprochement(nom: str) -> dict:
    """Correspondance PROBABLE par raison sociale (jamais certaine : IF/ICE non vérifiés)."""
    vide = {"correspondance": False}
    claim = _jetons(nom)
    if not claim:
        return vide
    meilleur, score_max = None, 0.0
    for emetteur in sorted({l["banque"] for l in charger()}):
        alias = set()
        for p in re.findall(r"\(([^)]+)\)", emetteur):
            alias |= _jetons(p)
        principal = _jetons(re.sub(r"\([^)]*\)", " ", emetteur))
        couverture = len(principal & claim) / len(principal) if principal else 0.0
        score = 1.0 if (alias & claim) else couverture
        if score < 0.85:  # faute de frappe : similarité de la chaîne normalisée
            ratio = difflib.SequenceMatcher(None, _norm(nom), _norm(re.sub(r"\([^)]*\)", " ", emetteur))).ratio()
            score = max(score, ratio if ratio >= 0.88 else 0.0)
        if score > score_max:
            meilleur, score_max = emetteur, score
    if not meilleur or score_max < 0.85:
        return vide
    exercices = sorted((l for l in charger() if l["banque"] == meilleur), key=lambda l: -l["annee"])
    return {"correspondance": True, "emetteur": meilleur, "score": round(score_max, 2), "exercices": exercices}
