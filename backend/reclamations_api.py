"""
GEIF — Traitement Automatique des Réclamations (IS & TVA)
Backend réel : FastAPI + SQLite + génération par LLM (Groq) + apprentissage bayésien (Beta-Bernoulli).

Lancer :
    pip install fastapi uvicorn requests --break-system-packages   (Windows: sans --break-system-packages si venv)
    $env:GROQ_API_KEY = "ta_cle_groq"      (PowerShell)
    uvicorn reclamations_api:app --reload --port 8010

Sans clé Groq : l'API fonctionne quand même (persistance, règles, apprentissage réels),
mais le texte du rapport/décision utilise un repli explicitement étiqueté "génération de repli"
au lieu du LLM, pour ne jamais prétendre qu'un texte vient du LLM s'il n'y vient pas vraiment.
"""

import os
import sqlite3
import json
from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import re
import chromadb
from sentence_transformers import SentenceTransformer

# ============================= RAG — RETRIEVAL RÉEL SUR LE CGI =============================
# Réutilise la base construite au Jour 1 (rag/chroma_db). Chemin relatif : ce fichier est
# dans backend/, la base est dans rag/ à la racine du repo.
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "rag", "chroma_db")
EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
SEUIL_CONFIANCE_RETRIEVAL = 2   # en-dessous de ce score, on flag "retrieval faible" pour le gestionnaire

_chroma_client = None
_collection_cgi = None
_modele_embedding = None

def _get_rag():
    """
    Chargement paresseux (lazy loading) : le modèle d'embedding (~470 Mo + PyTorch) n'est
    chargé qu'au PREMIER traitement de réclamation, pas au démarrage du serveur.
    Évite de saturer la RAM au lancement — surtout avec --reload qui duplique le processus.
    """
    global _chroma_client, _collection_cgi, _modele_embedding
    if _modele_embedding is None:
        print("[RAG] Premier chargement du modèle d'embedding et de la base CGI...")
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection_cgi = _chroma_client.get_collection(name="cgi")
        _modele_embedding = SentenceTransformer(EMBED_MODEL_NAME)
        print("[RAG] Prêt.")
    return _collection_cgi, _modele_embedding

MOTS_VIDES = {"de","la","le","les","des","du","une","un","et","pour","dans","à","au","aux",
              "ce","cette","ces","est","sont","par","sur","que","qui","avec","ou","en","plus","l'"}

def _mots_significatifs(texte: str):
    mots = re.findall(r"[a-zàâäéèêëïîôöùûüç]+", texte.lower())
    return [m[:6] if len(m) > 6 else m for m in mots if m not in MOTS_VIDES and len(m) > 2]

def rechercher_article_cgi(requete: str):
    """
    Retrieval hybride (identique en principe à rag/ingest_pdfs.py) : recherche sémantique
    large (60 candidats) + reclassement par mots-clés partagés (racinisés) avec bonus sur
    le titre de l'article. Retourne le meilleur chunk trouvé, avec un score de confiance.
    """
    mots_q = set(_mots_significatifs(requete))
    collection, modele = _get_rag()
    vecteur_q = modele.encode([requete]).tolist()
    resultats = collection.query(query_embeddings=vecteur_q, n_results=60)

    meilleur = None
    for rang, (doc, meta) in enumerate(zip(resultats["documents"][0], resultats["metadatas"][0])):
        mots_chunk = set(_mots_significatifs(doc))
        score = len(mots_q & mots_chunk)
        titre = doc[:80]
        score += len(mots_q & set(_mots_significatifs(titre))) * 3
        if meilleur is None or score > meilleur["score"] or (score == meilleur["score"] and rang < meilleur["rang"]):
            meilleur = {"score": score, "rang": rang, "article": meta["article"], "page": meta["page"], "texte": doc}

    return meilleur

DB_PATH = os.path.join(os.path.dirname(__file__), "reclamations.db")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

app = FastAPI(title="GEIF — Traitement Automatique (IS & TVA)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================= RÈGLES (articles CGI vérifiés) =============================
# Chaque règle a des paramètres alpha/beta réels (loi Bêta) : la confiance affichée
# est la moyenne de la postérieure alpha/(alpha+beta), pas un chiffre arbitraire.

RULES = {
    "IS-CALC":   {"tax": "IS",  "motif": "Erreur de calcul de la base imposable",
                  "article": "Art. 232 CGI",
                  "resume_legal": "l'administration peut réparer, dans le délai de prescription, les erreurs et omissions constatées dans la liquidation ou l'émission de l'impôt.",
                  "taux": 0.9, "alpha": 6.0, "beta": 2.0},
    "IS-CHARGE": {"tax": "IS",  "motif": "Charge déductible rejetée à tort",
                  "article": "Art. 10 CGI",
                  "resume_legal": "les charges d'exploitation, financières et non courantes remplissant les conditions de fond et de forme sont déductibles du résultat fiscal.",
                  "taux": 0.7, "alpha": 5.0, "beta": 2.5},
    "IS-DOUBLE": {"tax": "IS",  "motif": "Double imposition",
                  "article": "Art. 235 CGI",
                  "resume_legal": "le contribuable peut contester tout ou partie du montant mis à sa charge par voie de réclamation auprès de l'administration.",
                  "taux": 1.0, "alpha": 4.5, "beta": 2.0},
    "IS-DELAI":  {"tax": "IS",  "motif": "Délai de réclamation dépassé",
                  "article": "Art. 235 CGI",
                  "resume_legal": "la réclamation doit être introduite dans les six mois suivant la mise en recouvrement ; passé ce délai, elle est irrecevable.",
                  "taux": 0.0, "alpha": 9.0, "beta": 1.0},

    "TVA-DEDUC": {"tax": "TVA", "motif": "TVA déductible non prise en compte",
                  "article": "Art. 101 à 106 CGI",
                  "resume_legal": "la TVA ayant grevé les éléments du prix d'une opération imposable est déductible, sous réserve des conditions de fond et de forme prévues (facture conforme, lien avec l'activité imposable).",
                  "taux": 0.85, "alpha": 5.0, "beta": 2.0},
    "TVA-EXO":   {"tax": "TVA", "motif": "Opération exonérée taxée à tort",
                  "article": "Art. 91-92 CGI",
                  "resume_legal": "certaines opérations sont exonérées de TVA, avec ou sans droit à déduction selon leur nature ; une opération relevant de ces exonérations ne doit pas être taxée.",
                  "taux": 1.0, "alpha": 4.0, "beta": 2.0},
    "TVA-TAUX":  {"tax": "TVA", "motif": "Erreur sur le taux appliqué",
                  "article": "CGI — barème des taux de TVA",
                  "resume_legal": "chaque opération imposable relève d'un taux déterminé par le CGI selon sa nature ; l'application d'un taux erroné donne lieu à régularisation.",
                  "taux": 0.6, "alpha": 5.0, "beta": 2.5},
    "TVA-DELAI": {"tax": "TVA", "motif": "Délai de réclamation dépassé",
                  "article": "Art. 235 CGI",
                  "resume_legal": "la réclamation doit être introduite dans les six mois suivant la mise en recouvrement ; passé ce délai, elle est irrecevable.",
                  "taux": 0.0, "alpha": 9.0, "beta": 1.0},

    "IR-BAREME": {"tax": "IR",  "motif": "Erreur sur le barème appliqué",
                  "article": "CGI — barème de l'IR", "resume_legal": "à vérifier par retrieval.",
                  "taux": 0.8, "alpha": 5.0, "beta": 2.0},
    "IR-DEDUC":  {"tax": "IR",  "motif": "Déduction non prise en compte (charges, frais professionnels)",
                  "article": "CGI — déductions IR", "resume_legal": "à vérifier par retrieval.",
                  "taux": 0.75, "alpha": 5.0, "beta": 2.0},
    "IR-DOUBLE": {"tax": "IR",  "motif": "Double imposition",
                  "article": "Art. 235 CGI", "resume_legal": "à vérifier par retrieval.",
                  "taux": 1.0, "alpha": 4.5, "beta": 2.0},
    "IR-DELAI":  {"tax": "IR",  "motif": "Délai de réclamation dépassé",
                  "article": "Art. 235 CGI", "resume_legal": "à vérifier par retrieval.",
                  "taux": 0.0, "alpha": 9.0, "beta": 1.0},
}

# ============================= BASE DE DONNÉES =============================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reclamations (
            id TEXT PRIMARY KEY,
            contrib TEXT, ifn TEXT, tax TEXT, motif TEXT,
            montant REAL, date_mer TEXT, date_reclam TEXT,
            status TEXT DEFAULT 'nouvelle',
            rule_id TEXT, article TEXT, montant_degreve REAL,
            rapport TEXT, decision TEXT, source_texte TEXT,
            retrieval_score REAL, retrieval_page INTEGER,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id TEXT PRIMARY KEY, tax TEXT, motif TEXT, article TEXT,
            alpha REAL, beta REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id TEXT, tax TEXT, motif TEXT,
            texte_original TEXT, texte_corrige TEXT, outcome TEXT,
            created_at TEXT
        )
    """)
    cur = conn.execute("SELECT COUNT(*) c FROM rules")
    if cur.fetchone()["c"] == 0:
        for rid, r in RULES.items():
            conn.execute("INSERT INTO rules (id,tax,motif,article,alpha,beta) VALUES (?,?,?,?,?,?)",
                         (rid, r["tax"], r["motif"], r["article"], r["alpha"], r["beta"]))
    conn.commit()
    conn.close()

init_db()

# ============================= MODÈLES =============================

class NouvelleReclamation(BaseModel):
    contrib: str
    ifn: str
    tax: str          # "IS" ou "TVA"
    motif: str
    montant: float
    date_mer: str      # YYYY-MM-DD
    date_reclam: str

class DecisionGestionnaire(BaseModel):
    outcome: str        # "accept" | "modify" | "reject"
    decision_finale: Optional[str] = None

# ============================= MOTEUR DE RÈGLES =============================

def jours_entre(d1: str, d2: str) -> int:
    return (date.fromisoformat(d2) - date.fromisoformat(d1)).days

def choisir_regle(tax: str, motif: str, delai_jours: int):
    """
    Détermine le taux de dégrèvement applicable (règle métier), PUIS va chercher le vrai
    article du CGI par retrieval réel — au lieu d'un article écrit à la main comme avant.
    """
    if delai_jours > 180:
        rid = f"{tax}-DELAI"
        regle = dict(RULES[rid])
        requete_rag = "délai de réclamation six mois mise en recouvrement"
    else:
        rid = next((k for k, r in RULES.items() if r["tax"] == tax and r["motif"] == motif), None)
        if rid is None:
            rid = next(k for k, r in RULES.items() if r["tax"] == tax)
        regle = dict(RULES[rid])
        requete_rag = motif   # on cherche l'article réel correspondant au motif tel quel

    trouve = rechercher_article_cgi(requete_rag)
    if trouve:
        regle["article"] = trouve["article"]
        regle["resume_legal"] = trouve["texte"][:500].replace("\n", " ").strip()
        regle["retrieval_score"] = trouve["score"]
        regle["retrieval_page"] = trouve["page"]
    else:
        regle["retrieval_score"] = 0
        regle["retrieval_page"] = None

    return rid, regle

def recuperer_corrections_passees(rule_id: str, limite: int = 2):
    """
    Va chercher les dernières corrections du gestionnaire pour cette même règle —
    utilisées comme exemples (few-shot) pour que le LLM s'aligne sur le style et
    les ajustements que le gestionnaire a déjà faits sur des cas similaires.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT texte_original, texte_corrige, outcome FROM corrections WHERE rule_id=? ORDER BY created_at DESC LIMIT ?",
        (rule_id, limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def generer_texte_llm(d: dict, regle: dict, rid: str, montant_degreve: float, rejet: bool, delai_jours: int):
    """Appelle Groq pour rédiger le rapport + la décision. Repli explicite si pas de clé/échec réseau."""
    corrections = recuperer_corrections_passees(rid)
    bloc_corrections = ""
    if corrections:
        bloc_corrections = "\n\nEXEMPLES DE CORRECTIONS PRÉCÉDENTES DU GESTIONNAIRE (aligne-toi sur ce style/ajustement) :\n"
        for c in corrections:
            bloc_corrections += f"- Avant correction : {c['texte_original'][:200]}\n  Après correction ({c['outcome']}) : {c['texte_corrige'][:200]}\n"

    prompt = f"""Tu es un inspecteur des impôts à la Direction Régionale des Impôts de Rabat (Maroc).
Rédige, en français administratif marocain sobre, un RAPPORT D'INSTRUCTION puis une DÉCISION pour le dossier suivant.

Contribuable : {d['contrib']} (IF {d['ifn']})
Impôt concerné : {d['tax']}
Motif de la réclamation : {d['motif']}
Montant émis : {d['montant']:.2f} DH
Date de mise en recouvrement : {d['date_mer']}
Date de la réclamation : {d['date_reclam']}
Délai constaté : {delai_jours} jours
Base légale identifiée : {regle['article']} — {regle['resume_legal']}
Conclusion à motiver : {"réclamation irrecevable pour dépassement du délai légal" if rejet else f"dégrèvement de {montant_degreve:.2f} DH sur le montant émis"}
{bloc_corrections}
Réponds STRICTEMENT au format :
RAPPORT:
<le rapport d'instruction, 4 à 6 phrases>
DECISION:
<la décision, 3 à 4 phrases, formule administrative>
"""
    if not GROQ_API_KEY:
        return None, "repli_sans_cle"

    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 700,
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content, "groq_llm"
    except Exception as e:
        return None, f"repli_erreur:{e}"

def texte_repli(d: dict, regle: dict, montant_degreve: float, rejet: bool, delai_jours: int):
    """Texte déterministe, utilisé UNIQUEMENT si le LLM n'est pas disponible, et toujours étiqueté comme tel côté frontend."""
    if rejet:
        rapport = (f"Le dossier {d['contrib']} (IF {d['ifn']}) porte sur une réclamation {d['tax']} "
                   f"reçue {delai_jours} jours après la mise en recouvrement, soit au-delà du délai légal "
                   f"de six mois prévu à l'{regle['article']}. La réclamation est irrecevable en l'état.")
        decision = (f"DÉCISION : rejet de la réclamation pour forclusion, conformément à l'{regle['article']}.")
    else:
        rapport = (f"Le dossier {d['contrib']} (IF {d['ifn']}) invoque le motif « {d['motif']} » pour un montant "
                   f"émis de {d['montant']:.2f} DH. Sur la base de l'{regle['article']}, {regle['resume_legal']} "
                   f"Un dégrèvement de {montant_degreve:.2f} DH est proposé.")
        decision = (f"DÉCISION : dégrèvement de {montant_degreve:.2f} DH accordé sur le montant émis de "
                   f"{d['montant']:.2f} DH, conformément à l'{regle['article']}. Solde exigible : "
                   f"{d['montant'] - montant_degreve:.2f} DH.")
    return f"RAPPORT:\n{rapport}\nDECISION:\n{decision}"

# ============================= ENDPOINTS =============================

@app.post("/reclamations")
def creer_reclamation(r: NouvelleReclamation):
    conn = get_db()
    rid = "REC-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    conn.execute("""INSERT INTO reclamations (id,contrib,ifn,tax,motif,montant,date_mer,date_reclam,status,created_at)
                     VALUES (?,?,?,?,?,?,?,?,'nouvelle',?)""",
                 (rid, r.contrib, r.ifn, r.tax, r.motif, r.montant, r.date_mer, r.date_reclam,
                  datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"id": rid}

@app.get("/reclamations")
def lister_reclamations():
    conn = get_db()
    rows = conn.execute("SELECT * FROM reclamations ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/reclamations/{rec_id}/traiter")
def traiter_reclamation(rec_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM reclamations WHERE id=?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Réclamation introuvable")
    d = dict(row)

    delai = jours_entre(d["date_mer"], d["date_reclam"])
    rid, regle = choisir_regle(d["tax"], d["motif"], delai)
    rejet = regle["taux"] == 0.0
    montant_degreve = round(d["montant"] * regle["taux"], 2)

    llm_text, source = generer_texte_llm(d, regle, rid, montant_degreve, rejet, delai)
    if llm_text is None:
        llm_text = texte_repli(d, regle, montant_degreve, rejet, delai)

    if "DECISION:" in llm_text:
        rapport, decision = llm_text.split("DECISION:", 1)
        rapport = rapport.replace("RAPPORT:", "").strip()
        decision = decision.strip()
    else:
        rapport, decision = llm_text, ""

    conn.execute("""UPDATE reclamations SET status='attente', rule_id=?, article=?, montant_degreve=?,
                     rapport=?, decision=?, source_texte=?, retrieval_score=?, retrieval_page=? WHERE id=?""",
                 (rid, regle["article"], montant_degreve, rapport, decision, source,
                  regle.get("retrieval_score", 0), regle.get("retrieval_page"), rec_id))
    conn.commit()
    conn.close()
    return {"rule_id": rid, "article": regle["article"], "montant_degreve": montant_degreve,
            "rapport": rapport, "decision": decision, "source_texte": source, "delai_jours": delai,
            "retrieval_score": regle.get("retrieval_score", 0),
            "retrieval_faible": regle.get("retrieval_score", 0) < SEUIL_CONFIANCE_RETRIEVAL}

@app.post("/reclamations/{rec_id}/decision")
def valider_reclamation(rec_id: str, body: DecisionGestionnaire):
    conn = get_db()
    row = conn.execute("SELECT * FROM reclamations WHERE id=?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Réclamation introuvable")
    d = dict(row)

    if body.outcome not in ("accept", "modify", "reject"):
        raise HTTPException(400, "outcome invalide")

    status_map = {"accept": "validee", "modify": "modifiee", "reject": "rejetee"}
    decision_finale = body.decision_finale if body.outcome == "modify" and body.decision_finale else d["decision"]

    conn.execute("UPDATE reclamations SET status=?, decision=? WHERE id=?",
                 (status_map[body.outcome], decision_finale, rec_id))

    # ===== Boucle de correction : on garde une trace si le gestionnaire a modifié ou rejeté =====
    # (pas de trace pour "accept" — un accord tel quel n'apprend rien de nouveau au texte)
    if body.outcome in ("modify", "reject") and d.get("rule_id"):
        texte_corrige = decision_finale if body.outcome == "modify" else "(rejeté — voir motif du gestionnaire hors-système)"
        conn.execute(
            "INSERT INTO corrections (rule_id, tax, motif, texte_original, texte_corrige, outcome, created_at) VALUES (?,?,?,?,?,?,?)",
            (d["rule_id"], d["tax"], d["motif"], d.get("decision", ""), texte_corrige, body.outcome, datetime.now().isoformat())
        )

    # ===== Mise à jour bayésienne réelle (Beta-Bernoulli) =====
    rule = conn.execute("SELECT * FROM rules WHERE id=?", (d["rule_id"],)).fetchone()
    alpha, beta = rule["alpha"], rule["beta"]
    if body.outcome == "accept":
        alpha += 1.0
    elif body.outcome == "reject":
        beta += 1.0
    elif body.outcome == "modify":
        alpha += 0.5
        beta += 0.5
    conn.execute("UPDATE rules SET alpha=?, beta=? WHERE id=?", (alpha, beta, d["rule_id"]))

    conn.commit()
    conn.close()
    return {"status": status_map[body.outcome], "nouvelle_confiance": round(alpha / (alpha + beta), 4)}

@app.get("/regles")
def lister_regles():
    conn = get_db()
    rows = conn.execute("SELECT * FROM rules").fetchall()
    conn.close()
    out = []
    for row in rows:
        r = dict(row)
        r["confiance"] = round(r["alpha"] / (r["alpha"] + r["beta"]), 4)
        out.append(r)
    return out

@app.get("/corrections")
def lister_corrections():
    """Historique des corrections du gestionnaire — sert d'exemples few-shot pour le LLM."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM corrections ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/marche-ammc")
def marche_ammc():
    """
    Référentiel sectoriel : données financières réelles des banques marocaines cotées,
    issues du Pilier 9 (scraping AMMC -> parsing -> validation comptable -> DuckDB).

    NOTE MÉTHODOLOGIQUE : ces données n'alimentent PAS le moteur de décision des
    réclamations. Elles fournissent un contexte sectoriel consultable (ordres de
    grandeur réels sur des entreprises marocaines). Seuls les exercices ayant passé
    le contrôle d'identité comptable (Total Actif = Total Passif) sont marqués validés.
    """
    chemin_duckdb = os.path.join(os.path.dirname(__file__), "..", "data_engineering", "analytics.duckdb")
    if not os.path.exists(chemin_duckdb):
        return {"disponible": False,
                "message": "Base analytics.duckdb introuvable — le Pilier 9 (AMMC) n'est pas accessible depuis ce module.",
                "chemin_attendu": os.path.abspath(chemin_duckdb)}
    try:
        import duckdb
    except ImportError:
        return {"disponible": False, "message": "Module duckdb non installé (pip install duckdb)."}

    try:
        # read_only=True : ne bloque pas la base si Superset l'utilise en parallèle
        con = duckdb.connect(chemin_duckdb, read_only=True)
        lignes = con.execute("""
            SELECT bank, year, total_actif_current, resultat_net_current, validated
            FROM market_financials
            ORDER BY bank, year
        """).fetchall()
        colonnes = [c[0] for c in con.description]
        con.close()
        donnees = [dict(zip(colonnes, l)) for l in lignes]
        valides = [d for d in donnees if d.get("validated")]
        return {
            "disponible": True,
            "total_exercices": len(donnees),
            "exercices_valides": len(valides),
            "banques": sorted({d["bank"] for d in donnees}),
            "donnees": donnees,
        }
    except Exception as e:
        return {"disponible": False, "message": f"Erreur de lecture DuckDB : {e}"}

@app.get("/statistiques")
def statistiques():
    """
    Statistiques réelles calculées en SQL sur la base — aucune valeur simulée.
    Sert au tableau de bord et à la démonstration de l'impact du module.
    """
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) c FROM reclamations").fetchone()["c"]
    traitees = conn.execute("SELECT COUNT(*) c FROM reclamations WHERE status != 'nouvelle'").fetchone()["c"]

    par_statut = {r["status"]: r["c"] for r in conn.execute(
        "SELECT status, COUNT(*) c FROM reclamations GROUP BY status").fetchall()}

    par_impot = [dict(r) for r in conn.execute(
        """SELECT tax,
                  COUNT(*) AS nombre,
                  COALESCE(SUM(montant), 0) AS montant_emis,
                  COALESCE(SUM(montant_degreve), 0) AS montant_degreve
           FROM reclamations GROUP BY tax""").fetchall()]

    par_motif = [dict(r) for r in conn.execute(
        "SELECT motif, tax, COUNT(*) AS nombre FROM reclamations GROUP BY motif, tax ORDER BY nombre DESC").fetchall()]

    # Taux d'acceptation sans modification : le vrai indicateur de qualité du module
    valid_auto = conn.execute("SELECT COUNT(*) c FROM reclamations WHERE status='validee'").fetchone()["c"]
    modifiees = conn.execute("SELECT COUNT(*) c FROM reclamations WHERE status='modifiee'").fetchone()["c"]
    rejetees = conn.execute("SELECT COUNT(*) c FROM reclamations WHERE status='rejetee'").fetchone()["c"]
    closes = valid_auto + modifiees + rejetees
    taux_acceptation = round(valid_auto / closes, 4) if closes else None

    # Part des dossiers où le retrieval CGI était peu fiable (garde-fou déclenché)
    faibles = conn.execute(
        "SELECT COUNT(*) c FROM reclamations WHERE retrieval_score IS NOT NULL AND retrieval_score < ?",
        (SEUIL_CONFIANCE_RETRIEVAL,)).fetchone()["c"]

    montants = conn.execute(
        """SELECT COALESCE(SUM(montant),0) AS emis,
                  COALESCE(SUM(montant_degreve),0) AS degreve
           FROM reclamations WHERE status != 'nouvelle'""").fetchone()

    # Confiance par règle (moyenne bayésienne) + nombre de corrections associées
    regles_stats = []
    for r in conn.execute("SELECT * FROM rules").fetchall():
        r = dict(r)
        nb_corr = conn.execute("SELECT COUNT(*) c FROM corrections WHERE rule_id=?", (r["id"],)).fetchone()["c"]
        regles_stats.append({
            "id": r["id"], "tax": r["tax"], "motif": r["motif"],
            "confiance": round(r["alpha"] / (r["alpha"] + r["beta"]), 4),
            "observations": round(r["alpha"] + r["beta"] - 1, 1),   # -1 car alpha/beta partent d'un prior
            "corrections": nb_corr,
        })

    nb_corrections = conn.execute("SELECT COUNT(*) c FROM corrections").fetchone()["c"]
    conn.close()

    return {
        "total_reclamations": total,
        "traitees": traitees,
        "par_statut": par_statut,
        "par_impot": par_impot,
        "par_motif": par_motif,
        "taux_acceptation_sans_modification": taux_acceptation,
        "dossiers_retrieval_faible": faibles,
        "montant_total_emis": montants["emis"],
        "montant_total_degreve": montants["degreve"],
        "nombre_corrections_enregistrees": nb_corrections,
        "regles": regles_stats,
    }

@app.get("/health")
def health():
    return {"ok": True, "groq_configure": bool(GROQ_API_KEY)}
