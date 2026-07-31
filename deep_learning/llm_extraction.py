"""
GEIF — Extraction intelligente de champs par LLM (Groq — API gratuite)
============================================================================
Complète l'extraction par regex (cv_ocr/ocr.py), qui échoue sur les champs
en texte libre (motif, objet, arguments du contribuable). Un LLM comprend
le sens du texte OCR brut et peut extraire même quand la formulation varie
— contrairement à une regex qui exige un format figé.

Groq propose une API gratuite (avec limites de débit généreuses) exécutant
des modèles open-source (Llama, Mixtral...) à très grande vitesse.

⚠️ Nécessite une clé API Groq (gratuite) :
    1. Créer un compte sur https://console.groq.com
    2. Générer une clé API (section "API Keys")
    3. export GROQ_API_KEY="gsk_..."

Usage :
    export GROQ_API_KEY="gsk_..."
    python llm_extraction.py --text-file exemple_ocr.txt
"""
import json
import os

from groq import Groq

MODEL = "llama-3.3-70b-versatile"  # Modèle gratuit performant sur Groq (ajustable)

EXTRACTION_PROMPT = """Tu es un assistant d'extraction de données pour un service fiscal marocain.
Voici le texte brut (issu d'un OCR, potentiellement imparfait) d'un document fiscal.

Extrait UNIQUEMENT les champs suivants, sous forme de JSON strict (pas de texte autour) :
- type_document : le type de document (declaration, reclamation, avis_redressement, justificatif)
- motif : le motif principal de la demande, en une phrase concise (texte libre)
- montant : le montant principal mentionné (nombre, sans texte)
- reference : toute référence de dossier/affaire mentionnée

Si un champ est absent du texte, mets sa valeur à null. Réponds uniquement avec le JSON, sans balises markdown.

Texte du document :
---
{document_text}
---
"""


def extract_fields_llm(document_text: str, api_key: str = None) -> dict:
    """Extrait les champs structurés d'un texte OCR via un LLM (Groq).
    Retourne un dict avec les champs extraits, ou un dict d'erreur si l'appel
    échoue (ex : pas de clé API configurée)."""
    client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=300,
            temperature=0,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.format(document_text=document_text)
            }]
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e), "note": "Vérifie que GROQ_API_KEY est configurée (console.groq.com)."}


def compare_with_regex(document_text: str, regex_fields: dict, api_key: str = None) -> dict:
    """Compare l'extraction regex existante avec l'extraction LLM, pour
    documenter dans le rapport les cas où le LLM apporte une vraie valeur
    ajoutée (champs texte libre notamment)."""
    llm_fields = extract_fields_llm(document_text, api_key)
    return {
        "regex_extraction": regex_fields,
        "llm_extraction": llm_fields,
        "llm_found_more": (
            isinstance(llm_fields, dict) and "error" not in llm_fields
            and llm_fields.get("motif") and "motif" not in regex_fields
        ),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-file", required=True, help="Fichier .txt contenant le texte OCR brut")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    with open(args.text_file, encoding="utf-8") as f:
        text = f.read()

    result = extract_fields_llm(text, args.api_key)
    print(json.dumps(result, indent=2, ensure_ascii=False))
