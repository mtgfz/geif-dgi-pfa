"""
GEIF — RAG — Diagnostic rapide (n'écrase rien, ne réingère rien)
=======================================================================
Sert à répondre à deux questions précises :
  1. Les Articles 101 à 106 et 91-92 (TVA) sont-ils bien dans la base ?
  2. À quel rang ressortent-ils vraiment pour nos questions de test
     (rang 4 ? 10 ? absent des 15 premiers ?) — ça dit si c'est un problème
     de classement (résoluble) ou d'extraction (plus grave).

LANCEMENT :
    python debug_retrieval.py
"""

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_PATH = "./chroma_db"
EMBED_MODEL_NAME = "intfloat/multilingual-e5-base"

client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_collection(name="cgi")
modele = SentenceTransformer(EMBED_MODEL_NAME)

# ============================================================
# 1) Les articles existent-ils dans la base, tels quels ?
# ============================================================
print("=" * 60)
print("1) VÉRIFICATION DIRECTE — ces articles sont-ils indexés ?")
print("=" * 60)

for numero in ["Article 101", "Article 102", "Article 103", "Article 91", "Article 92"]:
    resultat = collection.get(where={"article": numero}, limit=1)
    if resultat["documents"]:
        extrait = resultat["documents"][0][:180].replace("\n", " ")
        print(f"\n✅ {numero} TROUVÉ (page {resultat['metadatas'][0]['page']}) :")
        print(f"   {extrait}...")
    else:
        print(f"\n❌ {numero} INTROUVABLE dans la base (problème d'extraction, pas de classement)")

# ============================================================
# 2) À quel rang ces articles sortent-ils vraiment ? (top 15, pas top 3)
# ============================================================
print("\n" + "=" * 60)
print("2) CLASSEMENT RÉEL — jusqu'au rang 15, pour voir si Art.101/91 apparaissent")
print("=" * 60)

questions = ["conditions de déduction de la TVA", "exonération de la TVA"]
for q in questions:
    vecteur_q = modele.encode(["query: " + q]).tolist()
    resultats = collection.query(query_embeddings=vecteur_q, n_results=15)
    print(f"\n🔎 Question : « {q} »")
    for rang, (meta, doc) in enumerate(zip(resultats["metadatas"][0], resultats["documents"][0]), start=1):
        marque = " <-- CIBLE" if meta["article"] in ("Article 101", "Article 102", "Article 103",
                                                        "Article 104", "Article 105", "Article 106",
                                                        "Article 91", "Article 92") else ""
        extrait = doc[:90].replace("\n", " ")
        print(f"   #{rang:>2} [{meta['article']}]{marque} {extrait}...")