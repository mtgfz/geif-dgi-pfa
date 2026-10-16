"""
Retrieval réel sur le CGI (Code Général des Impôts), via ChromaDB +
sentence-transformers. Chargement paresseux : le modèle n'est chargé qu'au
premier traitement, pas au démarrage du serveur (démarrage instantané).
"""
import re

from .config import settings

_chroma_client = None
_collection_cgi = None
_modele_embedding = None

MOTS_VIDES = {
    "de", "la", "le", "les", "des", "du", "une", "un", "et", "pour", "dans", "à", "au", "aux",
    "ce", "cette", "ces", "est", "sont", "par", "sur", "que", "qui", "avec", "ou", "en", "plus", "l'",
}


def _get_rag():
    global _chroma_client, _collection_cgi, _modele_embedding
    if _modele_embedding is None:
        import chromadb  # imports lourds : seulement au premier traitement
        from sentence_transformers import SentenceTransformer
        print("[RAG] Premier chargement du modèle d'embedding et de la base CGI...")
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        _collection_cgi = _chroma_client.get_collection(name="cgi")
        _modele_embedding = SentenceTransformer(settings.EMBED_MODEL_NAME)
        print("[RAG] Prêt.")
    return _collection_cgi, _modele_embedding


def _mots_significatifs(texte: str):
    mots = re.findall(r"[a-zàâäéèêëïîôöùûüç]+", texte.lower())
    return [m[:6] if len(m) > 6 else m for m in mots if m not in MOTS_VIDES and len(m) > 2]


def _classer_chunks(requete: str):
    """Retrieval hybride : sémantique large (60) + reclassement mots-clés/titre.
    Retourne la liste complète triée (meilleur d'abord), ou None si la base RAG
    n'est pas disponible."""
    try:
        collection, modele = _get_rag()
    except Exception as e:
        print(f"[RAG] Indisponible ({e}) — le texte utilisera le résumé légal codé en dur.")
        return None

    mots_q = set(_mots_significatifs(requete))
    vecteur_q = modele.encode([requete]).tolist()
    resultats = collection.query(query_embeddings=vecteur_q, n_results=60)

    classes = []
    for rang, (doc, meta) in enumerate(zip(resultats["documents"][0], resultats["metadatas"][0])):
        mots_chunk = set(_mots_significatifs(doc))
        score = len(mots_q & mots_chunk)
        score += len(mots_q & set(_mots_significatifs(doc[:80]))) * 3
        classes.append({"score": score, "rang": rang, "article": meta["article"], "page": meta["page"], "texte": doc})
    classes.sort(key=lambda c: (-c["score"], c["rang"]))
    return classes


def rechercher_article_cgi(requete: str):
    """Meilleur chunk trouvé, ou None si la base RAG n'est pas disponible."""
    classes = _classer_chunks(requete)
    return classes[0] if classes else None


def rechercher_articles_cgi(requete: str, k: int = 4):
    """Les k meilleurs articles distincts (un seul chunk par article).
    Liste vide si la base RAG n'est pas disponible."""
    classes = _classer_chunks(requete) or []
    vus, retenus = set(), []
    for c in classes:
        if c["article"] in vus:
            continue
        vus.add(c["article"])
        retenus.append(c)
        if len(retenus) >= k:
            break
    return retenus


def prechauffer() -> bool:
    """Charge le modèle d'embedding et la base du CGI en arrière-plan au démarrage de l'API,
    pour que la première question (assistant ou traitement) ne subisse pas ce délai."""
    try:
        _get_rag()
        print("[RAG] Base du CGI et modèle de recherche prêts.")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[RAG] Préchauffage impossible ({e}) — le RAG sera réessayé à la première utilisation.")
        return False


def _collection_seule():
    """Collection Chroma SANS charger le modèle d'embedding (suffisant pour compter et lister)."""
    if _collection_cgi is not None:
        return _collection_cgi
    import chromadb
    return chromadb.PersistentClient(path=settings.CHROMA_PATH).get_collection(name="cgi")


_etat_cache = {"valeur": None, "date": 0.0}


def etat_rag() -> dict:
    """Résumé de la base documentaire du CGI pour la page « Base de connaissances » (mis en cache 5 min)."""
    import os
    import time
    if _etat_cache["valeur"] and time.time() - _etat_cache["date"] < 300:
        return {**_etat_cache["valeur"], "modele_charge": _modele_embedding is not None}
    pdf = os.path.abspath(os.path.join(settings.CHROMA_PATH, "..", "data", "CGI.pdf"))
    info = {
        "disponible": False, "collection": "cgi", "modele": settings.EMBED_MODEL_NAME, "modele_charge": _modele_embedding is not None,
        "source": {"nom": os.path.basename(pdf), "taille_mo": round(os.path.getsize(pdf) / 1048576, 1)} if os.path.exists(pdf) else None,
    }
    try:
        metas = _collection_seule().get(include=["metadatas"])["metadatas"]
        articles = {m["article"] for m in metas if m.get("article") and m["article"] != "non détecté"}
        pages = [m["page"] for m in metas if m.get("page")]
        info.update(disponible=True, passages=len(metas), articles=len(articles),
                    page_min=min(pages) if pages else None, page_max=max(pages) if pages else None)
        _etat_cache.update(valeur=info, date=time.time())
    except Exception as e:  # noqa: BLE001
        info["message"] = f"Base du CGI inaccessible : {e}"
    return info


def rechercher_cgi(requete: str, k: int = 5) -> dict:
    """Recherche exploratoire : consultation directe d'un article (« Article 235 ») puis recherche sémantique."""
    import re
    resultats, vus = [], set()
    m = re.match(r"^\s*art(?:icle|\.)?\s*(\d+(?:\s*(?:bis|ter|quater))?)\s*$", requete, re.I)
    if m:
        numero = "Article " + " ".join(m.group(1).split())
        try:
            exact = _collection_seule().get(where={"article": numero}, include=["documents", "metadatas"])
            for doc, meta in zip(exact["documents"], exact["metadatas"]):
                resultats.append({"article": meta["article"], "page": meta["page"], "score": None, "texte": doc, "exact": True})
                vus.add(meta["article"])
        except Exception:  # noqa: BLE001 — article absent : on retombe sur la recherche sémantique
            pass
    for a in rechercher_articles_cgi(requete, k=k):
        if a["article"] not in vus:
            resultats.append({"article": a["article"], "page": a["page"], "score": a["score"], "texte": a["texte"], "exact": False})
    return {"requete": requete, "resultats": resultats[:k], "consultation_directe": bool(m)}
