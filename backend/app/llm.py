"""
Génération du rapport/décision. Utilise Groq si une clé est configurée ;
sinon un texte de repli explicitement étiqueté "repli_sans_cle" est utilisé
— jamais un texte présenté comme venant du LLM s'il n'en vient pas vraiment.
"""
import re
import requests

from .config import settings
from .database import col_corrections


def recuperer_corrections_passees(rule_id: str, limite: int = 2):
    """Dernières corrections du gestionnaire pour cette règle — exemples
    few-shot donnés au LLM pour qu'il s'aligne sur le style déjà validé."""
    rows = col_corrections.find({"rule_id": rule_id}).sort("created_at", -1).limit(limite)
    return [
        {"texte_original": r["texte_original"], "texte_corrige": r["texte_corrige"], "outcome": r["outcome"]}
        for r in rows
    ]


def _appeler_groq(prompt: str, max_tokens: int = 500, temperature: float = 0.4):
    """Appel Groq générique, réutilisé par le rapport/décision, l'assistant SIT
    et la reformulation assistée du gestionnaire."""
    if not settings.GROQ_API_KEY:
        print("[GROQ] Pas de clé configurée (GROQ_API_KEY vide).")
        return None
    try:
        resp = requests.post(
            settings.GROQ_URL,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": settings.GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[GROQ] Échec de l'appel : {type(e).__name__}: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[GROQ] Réponse brute du serveur : {e.response.text[:500]}")
        return None


_RE_DECISION = re.compile(r"(?im)^[\s*#>_\-]*D[ÉE]CISION(?:\s+PROPOS[ÉE]E)?[\s*_]*:[\s*_]*")
_RE_RAPPORT = re.compile(r"(?im)^[\s*#>_\-]*RAPPORT(?:\s+D['’]INSTRUCTION)?[\s*_]*:[\s*_]*")


def separer_rapport_decision(texte: str) -> tuple[str, str]:
    """Sépare la réponse du modèle en (rapport, décision), quelle que soit la mise en forme :
    « DECISION: », « DÉCISION : », « **Décision :** », « ### Décision proposée : »…
    Le marqueur doit commencer une ligne (« Décision contestée : » dans une phrase n'est pas un marqueur) et
    c'est le DERNIER marqueur qui compte. Si aucun n'est trouvé, la décision est vide : l'appelant décide quoi faire."""
    texte = (texte or "").strip()
    marqueurs = list(_RE_DECISION.finditer(texte))
    if marqueurs:
        m = marqueurs[-1]
        rapport, decision = texte[:m.start()], texte[m.end():]
    else:
        rapport, decision = texte, ""
    rapport = _RE_RAPPORT.sub("", rapport, count=1).strip()
    return rapport, decision.strip()


def assistant_sit_repondre(question: str, historique: list[dict] | None = None) -> dict:
    """Conseiller IA du portail contribuable : s'appuie sur le Code Général des Impôts (RAG) pour orienter
    (motifs, documents à fournir, délais). Ne rend aucune décision et ne remplace jamais un gestionnaire.

    Retourne {"reponse": str, "sources": [{article, page, extrait}], "genere": bool}.
    `genere` est False quand le modèle de langage est indisponible : on renvoie alors les passages
    du CGI les plus proches, sans les présenter comme une réponse rédigée."""
    from .rag import rechercher_articles_cgi  # import tardif : évite de charger le RAG tant qu'il n'est pas utile

    historique = historique or []
    # Question de suivi très courte (« et pour la TVA ? ») : on y joint la question précédente pour la recherche
    precedentes = [m.get("content", "") for m in historique if m.get("role") == "user"]
    requete = question if len(question.split()) >= 4 or not precedentes else f"{precedentes[-1]} {question}"
    sources = [
        {"article": a["article"], "page": a["page"], "extrait": a["texte"][:600].replace("\n", " ").strip()}
        for a in rechercher_articles_cgi(requete, k=3) if a["score"] >= 1
    ]

    fil = ""
    for m in historique[-4:]:
        fil += f"{'Contribuable' if m.get('role') == 'user' else 'Conseiller'} : {m.get('content', '')}\n"
    extraits = "\n".join(f"[{s['article']}, p. {s['page']}] {s['extrait']}" for s in sources) or "(aucun extrait pertinent trouvé)"
    prompt = f"""Tu es le conseiller virtuel du portail de la Direction Générale des Impôts (Maroc).
Tu aides les contribuables à déposer et suivre une réclamation (TVA, IS ou IR) : quel motif choisir, quels documents joindre
(la demande de dégrèvement est obligatoire, jusqu'à 5 documents optionnels avec description), les délais, et comment suivre leur dossier
avec la référence et le code de suivi reçus à la fin du dépôt.

Appuie-toi d'abord sur les EXTRAITS DU CGI ci-dessous lorsqu'ils sont pertinents et cite l'article concerné (ex. « Art. 235 CGI »).
Si les extraits ne permettent pas de répondre, dis-le simplement et oriente vers le gestionnaire. N'invente JAMAIS un article, un délai ou un montant.
Réponds en 2 à 4 phrases claires, en français, ton professionnel et rassurant. Tu ne rends JAMAIS de décision et tu ne donnes pas
d'avis juridique définitif : pour le fond du dossier, le gestionnaire tranchera.

EXTRAITS DU CGI :
{extraits}

{fil}
Question du contribuable : {question}
Réponse du conseiller :"""
    reponse = _appeler_groq(prompt, max_tokens=300, temperature=0.4)
    if reponse:
        return {"reponse": reponse, "sources": sources, "genere": True}
    if sources:
        texte = ("L'assistant n'est pas disponible pour le moment. Voici néanmoins les passages du Code Général des Impôts "
                 "les plus proches de votre question.")
    else:
        texte = ("L'assistant n'est pas disponible pour le moment. Vous pouvez déposer votre réclamation, puis la suivre "
                 "avec votre référence et votre code de suivi ; un gestionnaire l'examinera.")
    return {"reponse": texte, "sources": sources, "genere": False}


def reformuler_texte(rapport: str, decision: str, instruction: str) -> dict:
    """Aide le gestionnaire/chef à réviser le rapport et/ou la décision à
    partir d'une instruction en langage naturel, au lieu d'une réécriture
    manuelle complète. Garde le format I-IV du rapport."""
    prompt = f"""Tu es un inspecteur des impôts à la DGI (Maroc). Voici un rapport d'instruction et une décision
déjà rédigés pour un dossier de réclamation fiscale :

RAPPORT ACTUEL :
{rapport}

DÉCISION ACTUELLE :
{decision}

INSTRUCTION DU GESTIONNAIRE : {instruction}

Réécris le rapport ET la décision en appliquant cette instruction, en gardant le même format
(le rapport garde ses 4 sections I. Motifs.../II. Éléments.../III. Instruction.../IV. Avis...),
même style administratif sobre. Réponds STRICTEMENT au format :
RAPPORT:
<rapport complet révisé>
DECISION:
<décision complète révisée>"""
    reponse = _appeler_groq(prompt, max_tokens=700, temperature=0.3)
    if not reponse or "DECISION:" not in reponse:
        return {"ok": False, "rapport": rapport, "decision": decision}
    nouveau_rapport, nouvelle_decision = reponse.split("DECISION:", 1)
    return {"ok": True, "rapport": nouveau_rapport.replace("RAPPORT:", "").strip(), "decision": nouvelle_decision.strip()}


def generer_texte_llm(d: dict, regle: dict, rid: str, montant_degreve: float, rejet: bool, delai_jours: int, texte_pieces: str = ""):
    corrections = recuperer_corrections_passees(rid)
    bloc_corrections = ""
    if corrections:
        bloc_corrections = "\n\nEXEMPLES DE CORRECTIONS PRÉCÉDENTES DU GESTIONNAIRE (aligne-toi sur ce style/ajustement) :\n"
        for c in corrections:
            bloc_corrections += f"- Avant correction : {c['texte_original'][:200]}\n  Après correction ({c['outcome']}) : {c['texte_corrige'][:200]}\n"

    bloc_pieces = ""
    if texte_pieces:
        bloc_pieces = (
            "\n\nCONTENU DES PIÈCES JUSTIFICATIVES DÉPOSÉES PAR LE CONTRIBUABLE (extrait par OCR — "
            "peut contenir des imperfections de reconnaissance, à recouper avec les champs ci-dessus) :\n"
            f"{texte_pieces[:3000]}"
        )

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
{bloc_pieces}
{bloc_corrections}
Réponds STRICTEMENT au format, avec ces 4 sous-titres reproduits tels quels (ce sont les titres officiels du rapport d'instruction) :
RAPPORT:
I. Motifs et analyse de la demande
<2-3 phrases : rappelle le motif invoqué et le montant réclamé>
II. Éléments de l'enquête et renseignements tirés des documents d'assiette
<2-3 phrases : ce que montrent les pièces déposées, recoupées avec le dossier fiscal>
III. Instruction et argumentation
<2-3 phrases : analyse au regard de la base légale identifiée>
IV. Avis de l'inspecteur — révision proposée
<2-3 phrases : conclusion motivée, cohérente avec la conclusion à motiver ci-dessus>
DECISION:
<la décision, 3 à 4 phrases, formule administrative>
"""
    if not settings.GROQ_API_KEY:
        return None, "repli_sans_cle"

    try:
        resp = requests.post(
            settings.GROQ_URL,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": settings.GROQ_MODEL,
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
    if rejet:
        rapport = (
            f"I. Motifs et analyse de la demande\n"
            f"Le dossier {d['contrib']} (IF {d['ifn']}) porte sur une réclamation {d['tax']} invoquant le motif « {d['motif']} », "
            f"reçue {delai_jours} jours après la mise en recouvrement.\n\n"
            f"II. Éléments de l'enquête et renseignements tirés des documents d'assiette\n"
            f"L'examen du dossier fait apparaître que le délai légal de six mois prévu à l'{regle['article']} est dépassé.\n\n"
            f"III. Instruction et argumentation\n"
            f"{regle['resume_legal']}\n\n"
            f"IV. Avis de l'inspecteur — révision proposée\n"
            f"La réclamation est irrecevable en l'état pour forclusion."
        )
        decision = f"DÉCISION : rejet de la réclamation pour forclusion, conformément à l'{regle['article']}."
    else:
        rapport = (
            f"I. Motifs et analyse de la demande\n"
            f"Le dossier {d['contrib']} (IF {d['ifn']}) invoque le motif « {d['motif']} » pour un montant émis de {d['montant']:.2f} DH.\n\n"
            f"II. Éléments de l'enquête et renseignements tirés des documents d'assiette\n"
            f"Les pièces déposées ont été recoupées avec les éléments du dossier fiscal disponibles.\n\n"
            f"III. Instruction et argumentation\n"
            f"Sur la base de l'{regle['article']}, {regle['resume_legal']}\n\n"
            f"IV. Avis de l'inspecteur — révision proposée\n"
            f"Un dégrèvement de {montant_degreve:.2f} DH est proposé sur le montant émis de {d['montant']:.2f} DH."
        )
        decision = (
            f"DÉCISION : dégrèvement de {montant_degreve:.2f} DH accordé sur le montant émis de "
            f"{d['montant']:.2f} DH, conformément à l'{regle['article']}. Solde exigible : "
            f"{d['montant'] - montant_degreve:.2f} DH."
        )
    return f"RAPPORT:\n{rapport}\nDECISION:\n{decision}"
