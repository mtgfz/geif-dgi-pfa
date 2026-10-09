"""
Retrieval réel sur le CGI (Code Général des Impôts), via ChromaDB +
sentence-transformers. Chargement paresseux : le modèle n'est chargé qu'au
premier traitement, pas au démarrage du serveur (démarrage instantané).
"""
import re

import chromadb
from sentence_transformers import SentenceTransformer

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
        print("[RAG] Premier chargement du modèle d'embedding et de la base CGI...")
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        _collection_cgi = _chroma_client.get_collection(name="cgi")
        _modele_embedding = SentenceTransformer(settings.EMBED_MODEL_NAME)
        print("[RAG] Prêt.")
    return _collection_cgi, _modele_embedding


def _mots_significatifs(texte: str):
    mots = re.findall(r"[a-zàâäéèêëïîôöùûüç]+", texte.lower())
    return [m[:6] if len(m) > 6 else m for m in mots if m not in MOTS_VIDES and len(m) > 2]


def rechercher_article_cgi(requete: str):
    """Retrieval hybride : sémantique large (60) + reclassement mots-clés/titre.
    Retourne le meilleur chunk trouvé, ou None si la base RAG n'est pas disponible."""
    try:
        collection, modele = _get_rag()
    except Exception as e:
        print(f"[RAG] Indisponible ({e}) — le texte utilisera le résumé légal codé en dur.")
        return None

    mots_q = set(_mots_significatifs(requete))
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
