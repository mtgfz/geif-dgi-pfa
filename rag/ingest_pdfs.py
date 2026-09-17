"""
GEIF — RAG Pipeline — Jour 1 : Ingestion du CGI
=======================================================================

CE QUE FAIT CE SCRIPT (en 4 étapes) :
  1. EXTRACTION : lit le texte du PDF du CGI, page par page
  2. DÉCOUPAGE  : coupe le texte en petits morceaux ("chunks") avec chevauchement
  3. EMBEDDING  : convertit chaque chunk en vecteur numérique (sens du texte)
  4. STOCKAGE   : sauvegarde le tout dans une base vectorielle locale (ChromaDB)

À la fin, tu as un dossier `chroma_db/` que le reste du pipeline (Jour 2) va interroger.

INSTALLATION (une seule fois) :
    pip install chromadb pdfplumber sentence-transformers --break-system-packages

LANCEMENT :
    python ingest_pdfs.py --cgi chemin/vers/CGI.pdf
"""

import argparse
import re
import pdfplumber
import chromadb
from sentence_transformers import SentenceTransformer

# ============================================================
# ÉTAPE 0 — Config
# ============================================================
# Modèle d'embedding multilingue, comprend bien le français juridique.
# Tourne en local sur ton PC — pas de clé API, pas de coût par appel.
EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
# Note : "intfloat/multilingual-e5-base" a été testé et a donné de MOINS bons résultats
# sur ce corpus (CGI marocain) que ce modèle plus simple — gardé par choix empirique,
# pas par défaut. Une "meilleure" architecture en théorie ne l'est pas toujours en pratique.

CHUNK_SIZE = 700       # caractères par chunk — assez pour capturer un article complet ou presque
CHUNK_OVERLAP = 100     # chevauchement entre chunks consécutifs — évite de couper une phrase clé en deux

CHROMA_PATH = "./chroma_db"   # dossier où la base vectorielle est sauvegardée sur disque


# ============================================================
# ÉTAPE 1 — EXTRACTION : PDF -> texte, page par page
# ============================================================
def extraire_texte_pdf(chemin_pdf: str):
    """
    Retourne une liste de dicts : [{"texte": "...", "page": 12}, ...]
    On garde le numéro de page pour pouvoir citer précisément plus tard
    (ex: "Art. 235 CGI, page 87").
    """
    pages = []
    print(f"[extraction] Lecture de {chemin_pdf} ...")
    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text() or ""
            texte = texte.strip()
            if texte:  # on ignore les pages vides (pages de garde, séparateurs...)
                pages.append({"texte": texte, "page": i + 1})
    print(f"[extraction] {len(pages)} pages non-vides extraites.")
    return pages


# ============================================================
# ÉTAPE 2 — DÉCOUPAGE : article par article (pas par taille fixe)
# ============================================================
# Pourquoi ce changement : un découpage à taille fixe coupe parfois un article
# en deux morceaux, ou mélange la fin d'un article avec le début du suivant —
# le sens devient flou et le retrieval sort le mauvais article.
# Ici, chaque "Article N" du CGI devient son propre chunk naturel.

MOTIF_ARTICLE = re.compile(r"(?=\n?Article\s+\d+[a-zA-Z]?(?:\s+(?:bis|ter|quater))?\s*[\-–:.])")

SOUS_CHUNK_TAILLE = 500      # le modèle MiniLM tronque silencieusement au-delà de ~128 tokens
                               # (~700 caractères en français) — on reste bien en-dessous pour
                               # être sûr qu'aucun article ne soit coupé avant même d'être embeddé
SOUS_CHUNK_CHEVAUCHEMENT = 80

def decouper_en_chunks(texte: str, taille=SOUS_CHUNK_TAILLE, chevauchement=SOUS_CHUNK_CHEVAUCHEMENT):
    """Sous-découpage de secours, utilisé UNIQUEMENT si un article dépasse SOUS_CHUNK_TAILLE caractères."""
    chunks = []
    debut = 0
    while debut < len(texte):
        fin = debut + taille
        chunks.append(texte[debut:fin])
        debut += (taille - chevauchement)
    return chunks


def construire_chunks_avec_metadata(pages: list):
    """
    Concatène toutes les pages en un seul texte (avec des marqueurs de page invisibles
    pour retrouver ensuite sur quelle page chaque article commence), puis découpe
    ce texte au niveau de chaque "Article N" plutôt qu'à taille fixe.
    """
    # 1) Concaténation avec marqueurs de page — ex: [[PAGE:87]] avant le texte de la page 87
    texte_complet = ""
    for page_info in pages:
        texte_complet += f"[[PAGE:{page_info['page']}]]\n{page_info['texte']}\n"

    # 2) Découpage au niveau de chaque "Article N" (lookahead : le séparateur reste dans le morceau suivant)
    morceaux_bruts = MOTIF_ARTICLE.split(texte_complet)
    morceaux_bruts = [m for m in morceaux_bruts if m.strip()]

    print(f"[découpage] {len(morceaux_bruts)} articles/sections détectés dans le texte.")

    tous_les_chunks = []
    articles_deja_vus = set()   # pour détecter les doublons d'annexe (numérotation qui recommence à 1)
    doublons_ignores = 0

    for morceau in morceaux_bruts:
        # Retrouver le numéro d'article (s'il y en a un dans ce morceau)
        match_article = re.search(r"Article\s+(\d+[a-zA-Z]?(?:\s*bis|\s*ter|\s*quater)?)", morceau)
        article_detecte = f"Article {match_article.group(1)}" if match_article else None

        # ===== Filtre anti-annexe =====
        # Si ce numéro d'article a déjà été vu plus tôt dans le document, c'est presque
        # certainement une annexe avec sa propre numérotation (ex: Article 2 d'un arrêté
        # annexé, qui n'a rien à voir avec l'Article 2 du CGI lui-même). On l'ignore.
        if article_detecte is not None:
            if article_detecte in articles_deja_vus:
                doublons_ignores += 1
                continue
            articles_deja_vus.add(article_detecte)

        # Retrouver la première page mentionnée dans ce morceau (approximation : page de début)
        match_page = re.search(r"\[\[PAGE:(\d+)\]\]", morceau)
        page_detectee = int(match_page.group(1)) if match_page else None

        # Nettoyer les marqueurs de page avant de stocker le texte
        texte_propre = re.sub(r"\[\[PAGE:\d+\]\]\n?", "", morceau).strip()
        if not texte_propre:
            continue

        # Si l'article est trop long, on le sous-découpe (rare, mais certains articles sont très longs)
        if len(texte_propre) > SOUS_CHUNK_TAILLE:
            sous_morceaux = decouper_en_chunks(texte_propre)
            for sous_morceau in sous_morceaux:
                tous_les_chunks.append({
                    "texte": sous_morceau,
                    "page": page_detectee,
                    "article": article_detecte,
                })
        else:
            tous_les_chunks.append({
                "texte": texte_propre,
                "page": page_detectee,
                "article": article_detecte,
            })

    print(f"[découpage] {doublons_ignores} doublons d'annexe ignorés (numérotation qui recommence).")
    return tous_les_chunks


# ============================================================
# ÉTAPE 3 & 4 — EMBEDDING + STOCKAGE dans ChromaDB
# ============================================================
def indexer_chunks(chunks: list):
    print(f"[embedding] Chargement du modèle {EMBED_MODEL_NAME} (première fois = télécharge le modèle, ~470 Mo)...")
    modele = SentenceTransformer(EMBED_MODEL_NAME)

    print(f"[embedding] Calcul des vecteurs pour {len(chunks)} chunks...")
    # (Pas de préfixe "passage:" ici — cette convention est spécifique aux modèles e5,
    # ça n'aiderait pas MiniLM et ajouterait juste du bruit dans le texte encodé.)
    textes_bruts = [c["texte"] for c in chunks]
    vecteurs = modele.encode(textes_bruts, show_progress_bar=True, batch_size=32)

    print("[stockage] Connexion à ChromaDB (base locale persistante)...")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # "get_or_create" : si tu relances le script, ça met à jour la même collection
    # au lieu d'en créer une nouvelle à chaque fois.
    collection = client.get_or_create_collection(name="cgi")

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {"page": c["page"] if c["page"] is not None else 0, "article": c["article"] or "non détecté"}
        for c in chunks
    ]

    collection.upsert(
        ids=ids,
        embeddings=vecteurs.tolist(),
        documents=textes_bruts,
        metadatas=metadatas,
    )
    print(f"[stockage] {len(chunks)} chunks indexés dans '{CHROMA_PATH}/'. Terminé ✅")
    return collection


# ============================================================
# ÉTAPE 5 — TEST : recherche hybride (sémantique + mots-clés)
# ============================================================
# Pourquoi hybride : la similarité sémantique pure se fait parfois avoir par un chunk
# qui "parle du même sujet en gros" sans être la bonne réponse précise. En combinant
# avec un vrai comptage de mots-clés de la question retrouvés dans le texte, on fait
# remonter les articles qui contiennent littéralement les termes recherchés.

MOTS_VIDES = {"de","la","le","les","des","du","une","un","et","pour","dans","à","au","aux",
              "ce","cette","ces","est","sont","par","sur","que","qui","avec","ou","en","plus","l'"}

def mots_significatifs(texte: str):
    """
    Racinisation simple (troncature) : on coupe chaque mot à ~6 lettres pour que
    "déduction", "déductible", "déduire" soient reconnus comme apparentés, de même
    que "exonération" / "exonérées" / "exonérés". Une vraie lemmatisation (spaCy)
    serait plus précise, mais cette troncature suffit largement pour du retrieval
    et évite d'ajouter une dépendance lourde.
    """
    mots = re.findall(r"[a-zàâäéèêëïîôöùûüç]+", texte.lower())
    return [m[:6] if len(m) > 6 else m for m in mots if m not in MOTS_VIDES and len(m) > 2]

def tester_retrieval(collection, modele):
    questions_test = [
        "délai pour déposer une réclamation fiscale",
        "conditions de déduction de la TVA",
        "charges déductibles pour l'impôt sur les sociétés",
        "exonération de la TVA",
    ]
    print("\n" + "=" * 60)
    print("TEST DE RETRIEVAL HYBRIDE (sémantique + mots-clés)")
    print("=" * 60)
    for q in questions_test:
        mots_q = set(mots_significatifs(q))
        vecteur_q = modele.encode([q]).tolist()
        # 1) large filet sémantique — 60 candidats, pour maximiser les chances que le
        #    bon chunk (même mal classé sémantiquement) soit au moins dans le lot
        resultats = collection.query(query_embeddings=vecteur_q, n_results=60)

        candidats = []
        for rang_semantique, (doc, meta) in enumerate(zip(resultats["documents"][0], resultats["metadatas"][0])):
            mots_chunk = set(mots_significatifs(doc))
            score_motscles = len(mots_q & mots_chunk)

            # Bonus titre : les ~80 premiers caractères contiennent souvent "Article N.- Titre",
            # l'endroit le plus fiable pour juger la pertinence en droit fiscal
            # (ex: "Article 91.- Exonérations sans droit à déduction" matche directement la question).
            titre = doc[:80]
            mots_titre = set(mots_significatifs(titre))
            bonus_titre = len(mots_q & mots_titre) * 3

            score_total = score_motscles + bonus_titre
            candidats.append((score_total, -rang_semantique, doc, meta))

        # 2) re-classement : d'abord par score de mots-clés, puis par rang sémantique d'origine
        candidats.sort(key=lambda c: (c[0], c[1]), reverse=True)

        print(f"\n🔎 Question : « {q} »")
        for score_total, rang_neg, doc, meta in candidats[:5]:
            extrait = doc[:140].replace("\n", " ")
            print(f"   [{meta['article']} · p.{meta['page']} · score {score_total}] {extrait}...")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cgi", required=True, help="Chemin vers le PDF du CGI")
    args = parser.parse_args()

    pages_cgi = extraire_texte_pdf(args.cgi)

    chunks = construire_chunks_avec_metadata(pages_cgi)
    print(f"[découpage] {len(chunks)} chunks créés au total.")

    collection = indexer_chunks(chunks)

    modele = SentenceTransformer(EMBED_MODEL_NAME)
    tester_retrieval(collection, modele)