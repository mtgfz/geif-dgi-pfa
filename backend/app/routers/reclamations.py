import base64
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..config import settings
from ..database import col_corrections, col_documents, col_reclamations, col_rules, sans_id_mongo
from ..email_service import envoyer_email_confirmation_depot, envoyer_email_decision
from ..llm import generer_texte_llm, reformuler_texte, texte_repli
from ..models import DecisionGestionnaire, NouvelleReclamation, ReformulationRequest
from ..ocr import extraire_texte_document
from ..rag import rechercher_article_cgi
from ..rules_engine import appliquer_feedback, choisir_regle_id, jours_entre
from ..security import get_current_user, require_roles

router = APIRouter(prefix="/reclamations", tags=["reclamations"])

# Statuts possibles, dans l'ordre du circuit :
#   nouvelle -> attente (traité par IA) -> attente_chef_secteur -> attente_chef_subdivision
#   -> validee_finale   (ou "rejetee" à n'importe quelle étape de validation)


def _choisir_regle_avec_rag(tax: str, motif: str, delai_jours: int):
    """Comme rules_engine.choisir_regle_id, mais enrichit la règle trouvée
    avec l'article réel retrouvé par le RAG (utilisé uniquement au traitement,
    pas à la prédiction rapide)."""
    rid = choisir_regle_id(tax, motif, delai_jours)
    if not rid:
        return None, None
    regle = dict(col_rules.find_one({"_id": rid}))
    requete_rag = "délai de réclamation six mois mise en recouvrement" if delai_jours > 180 else motif

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


def _generer_cle_verification() -> str:
    """Code court, tapable à la main (ex: 7F3K-9QRT), envoyé uniquement par
    e-mail — sert de deuxième secret en plus de la référence pour consulter
    la décision finale et écrire dans l'espace de discussion."""
    brut = secrets.token_hex(4).upper()
    return f"{brut[:4]}-{brut[4:]}"


# ---------- endpoints publics : dépôt et consultation (portail SIT) ----------

@router.post("")
def creer_reclamation(r: NouvelleReclamation):
    rid = "REC-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    doc = {
        "_id": rid, "id": rid,
        "contrib": r.contrib, "ifn": r.ifn, "tax": r.tax, "motif": r.motif,
        "montant": r.montant, "date_mer": r.date_mer, "date_reclam": r.date_reclam,
        "email": r.email,
        "cle_verification": _generer_cle_verification(),
        "status": "nouvelle", "rule_id": None, "article": None, "montant_degreve": None,
        "rapport": None, "decision": None, "source_texte": None,
        "retrieval_score": None, "retrieval_page": None,
        "gestionnaire_choisi": None,
        "lu_par_contribuable": False, "date_lecture": None,
        "email_envoye": False,
        "email_confirmation_envoye": False,
        "created_at": datetime.now().isoformat(),
    }
    col_reclamations.insert_one(doc)

    # Confirmation de dépôt envoyée tout de suite (référence + clé de
    # vérification) — ne bloque jamais la réponse : si SMTP échoue ou n'est
    # pas configuré, le contribuable garde quand même la clé affichée à
    # l'écran juste après (voir renderDepotConfirmation côté frontend).
    confirmation_envoyee = envoyer_email_confirmation_depot(
        destinataire=r.email, contribuable=r.contrib, rec_id=rid, cle_verification=doc["cle_verification"],
    )
    if confirmation_envoyee:
        col_reclamations.update_one({"_id": rid}, {"$set": {"email_confirmation_envoye": True}})

    # La clé n'est jamais renvoyée dans une réponse listée/publique ailleurs —
    # uniquement ici, à la création, pour affichage immédiat + envoi par e-mail.
    return {"id": rid, "cle_verification": doc["cle_verification"], "email_confirmation_envoye": confirmation_envoyee}


@router.get("")
def lister_reclamations(status: str | None = None, _user: dict = Depends(get_current_user)):
    """Réservé aux comptes internes. `status` accepte une liste séparée par
    virgules (ex: status=nouvelle,attente) pour que chaque rôle ne charge que
    la file qui le concerne côté frontend."""
    query = {"status": {"$in": status.split(",")}} if status else {}
    rows = col_reclamations.find(query).sort("created_at", -1)
    return [sans_id_mongo(r) for r in rows]


@router.post("/{rec_id}/documents")
async def deposer_documents(
    rec_id: str,
    demande_degrevement: UploadFile = File(..., description="Document obligatoire — demande de dégrèvement"),
    description_demande: str = Form(..., max_length=settings.DOCUMENT_DESCRIPTION_MAX),
    documents_optionnels: list[UploadFile] = File(default=[]),
    descriptions_optionnelles: list[str] = Form(default=[]),
):
    """Endpoint public du portail SIT : reçoit la demande de dégrèvement
    (obligatoire) et jusqu'à 5 documents optionnels, chacun avec sa
    description. Chaque fichier est OCRisé immédiatement — le texte sera
    utilisé au traitement pour enrichir le rapport généré."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    if col_documents.count_documents({"reclamation_id": rec_id}) > 0:
        raise HTTPException(409, "Les documents de ce dossier ont déjà été déposés — dépôt bloqué pour éviter les doublons.")

    if len(documents_optionnels) > settings.DOCUMENT_MAX_OPTIONNELS:
        raise HTTPException(400, f"Maximum {settings.DOCUMENT_MAX_OPTIONNELS} documents optionnels.")
    if len(descriptions_optionnelles) != len(documents_optionnels):
        raise HTTPException(400, "Chaque document optionnel doit avoir exactement une description.")

    # Filet de sécurité : au cas où d'anciens doublons existeraient déjà en base
    # (créés avant ce correctif), on nettoie avant d'insérer le nouveau dépôt.
    col_documents.delete_many({"reclamation_id": rec_id})

    tous = [(demande_degrevement, description_demande, True)] + [
        (f, desc, False) for f, desc in zip(documents_optionnels, descriptions_optionnelles)
    ]

    enregistres = []
    for fichier, description, obligatoire in tous:
        if fichier.content_type not in settings.DOCUMENT_TYPES_AUTORISES:
            raise HTTPException(400, f"Format non autorisé pour « {fichier.filename} » (PDF, PNG ou JPG uniquement).")
        contenu = await fichier.read()
        if len(contenu) > settings.DOCUMENT_TAILLE_MAX_MO * 1024 * 1024:
            raise HTTPException(400, f"« {fichier.filename} » dépasse {settings.DOCUMENT_TAILLE_MAX_MO} Mo.")
        if not description or len(description) > settings.DOCUMENT_DESCRIPTION_MAX:
            raise HTTPException(400, f"Description invalide pour « {fichier.filename} » (max {settings.DOCUMENT_DESCRIPTION_MAX} caractères).")

        texte_ocr = extraire_texte_document(contenu, fichier.content_type, fichier.filename)

        doc = {
            "reclamation_id": rec_id,
            "filename": fichier.filename,
            "content_type": fichier.content_type,
            "description": description,
            "obligatoire": obligatoire,
            "contenu_b64": base64.b64encode(contenu).decode(),
            "texte_ocr": texte_ocr,
            "uploaded_at": datetime.now().isoformat(),
        }
        col_documents.insert_one(doc)
        enregistres.append({"filename": fichier.filename, "description": description, "ocr_apercu": texte_ocr[:120]})

    return {"reclamation_id": rec_id, "documents_enregistres": enregistres}


@router.get("/{rec_id}/documents")
def lister_documents(rec_id: str, _user: dict = Depends(get_current_user)):
    """Réservé au gestionnaire/chefs — la liste des pièces jointes, sans le
    contenu binaire (juste métadonnées + texte OCR) pour rester léger."""
    rows = col_documents.find({"reclamation_id": rec_id})
    return [
        {
            "filename": r["filename"], "description": r["description"], "obligatoire": r["obligatoire"],
            "content_type": r["content_type"], "texte_ocr": r["texte_ocr"], "uploaded_at": r["uploaded_at"],
        }
        for r in rows
    ]


# ---------- traitement automatique (gestionnaire) ----------

@router.post("/{rec_id}/traiter")
def traiter_reclamation(rec_id: str, user: dict = Depends(get_current_user)):
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable")

    delai = jours_entre(d["date_mer"], d["date_reclam"])
    rid, regle = _choisir_regle_avec_rag(d["tax"], d["motif"], delai)
    if not rid:
        raise HTTPException(422, "Aucune règle applicable pour ce type d'impôt.")

    rejet = regle["taux"] == 0.0
    montant_degreve = round(d["montant"] * regle["taux"], 2)

    pieces = list(col_documents.find({"reclamation_id": rec_id}))
    texte_pieces = "\n\n".join(
        f"--- Document « {p['description']} » ({p['filename']}) ---\n{p['texte_ocr']}" for p in pieces
    ) if pieces else ""

    llm_text, source = generer_texte_llm(d, regle, rid, montant_degreve, rejet, delai, texte_pieces)
    if llm_text is None:
        llm_text = texte_repli(d, regle, montant_degreve, rejet, delai)

    if "DECISION:" in llm_text:
        rapport, decision = llm_text.split("DECISION:", 1)
        rapport = rapport.replace("RAPPORT:", "").strip()
        decision = decision.strip()
    else:
        rapport, decision = llm_text, ""

    col_reclamations.update_one({"_id": rec_id}, {"$set": {
        "status": "attente", "rule_id": rid, "article": regle["article"], "montant_degreve": montant_degreve,
        "rapport": rapport, "decision": decision, "rapport_original": rapport, "decision_original": decision,
        "source_texte": source,
        "traite_par": user["username"],
        "retrieval_score": regle.get("retrieval_score", 0), "retrieval_page": regle.get("retrieval_page"),
    }})

    return {
        "rule_id": rid, "article": regle["article"], "montant_degreve": montant_degreve,
        "rapport": rapport, "decision": decision, "source_texte": source, "delai_jours": delai,
        "retrieval_score": regle.get("retrieval_score", 0),
        "retrieval_faible": regle.get("retrieval_score", 0) < settings.SEUIL_CONFIANCE_RETRIEVAL,
    }


# ---------- chaîne de validation hiérarchique ----------
#
# 1) Gestionnaire (/decision)            : seul niveau qui déclenche l'apprentissage
#    bayésien (appliquer_feedback) — c'est la décision de première ligne, celle qui
#    doit apprendre le plus vite des cas rencontrés.
# 2) Chef de secteur (/decision-secteur) : contrôle et peut corriger le texte, mais
#    ne rejoue pas la mise à jour bayésienne — sinon un même dossier compterait deux
#    fois dans l'apprentissage de la règle. Sa correction est tout de même journalisée
#    (col_corrections) pour rester disponible comme exemple au LLM.
# 3) Chef de subdivision (/decision-subdivision) : dernier verrou. Une fois validé ici,
#    la décision est finale, envoyée par e-mail au contribuable, et visible sur le SIT.

@router.post("/{rec_id}/reformuler")
def reformuler(rec_id: str, body: ReformulationRequest, user: dict = Depends(get_current_user)):
    """Assistant IA pour le gestionnaire/chef : réécrit rapport+décision selon
    une instruction, au lieu d'une réécriture manuelle. Ne sauvegarde rien
    tant que le gestionnaire n'a pas cliqué « Enregistrer »."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    if d["status"] in ("nouvelle", "validee_finale", "rejetee"):
        raise HTTPException(409, "Ce dossier n'est pas modifiable dans son état actuel.")
    resultat = reformuler_texte(d.get("rapport", ""), d.get("decision", ""), body.instruction)
    if not resultat["ok"]:
        raise HTTPException(503, "Assistant IA indisponible pour le moment (clé Groq non configurée ou service injoignable).")
    return resultat


@router.post("/{rec_id}/brouillon")
def sauvegarder_brouillon(rec_id: str, body: DecisionGestionnaire, user: dict = Depends(get_current_user)):
    """Enregistre le rapport et/ou la décision en cours d'édition — n'avance
    pas le workflow, ne notifie personne. Écrase toujours la version précédente
    (une seule version courante, pas d'historique) : la dernière modification
    enregistrée est celle qui sera envoyée au niveau suivant."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    if d["status"] in ("nouvelle", "validee_finale", "rejetee"):
        raise HTTPException(409, "Ce dossier n'est pas modifiable dans son état actuel.")
    updates = {}
    if body.rapport_finale is not None:
        updates["rapport"] = body.rapport_finale
    if body.decision_finale is not None:
        updates["decision"] = body.decision_finale
    if not updates:
        raise HTTPException(400, "Rien à enregistrer.")
    col_reclamations.update_one({"_id": rec_id}, {"$set": updates})
    return {"enregistre": True}


@router.post("/{rec_id}/decision")
def valider_reclamation(rec_id: str, body: DecisionGestionnaire, user: dict = Depends(require_roles("gestionnaire"))):
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable")
    if body.outcome not in ("accept", "reject"):
        raise HTTPException(400, "outcome invalide")

    status_map = {"accept": "attente_chef_secteur", "reject": "rejetee"}
    col_reclamations.update_one({"_id": rec_id}, {"$set": {
        "status": status_map[body.outcome], "valide_par_gestionnaire": user["username"],
    }})

    modifie = body.outcome == "accept" and d.get("rule_id") and (
        d.get("decision") != d.get("decision_original") or d.get("rapport") != d.get("rapport_original")
    )
    if modifie:
        col_corrections.insert_one({
            "rule_id": d["rule_id"], "tax": d["tax"], "motif": d["motif"],
            "texte_original": d.get("decision_original", ""), "texte_corrige": d.get("decision", ""),
            "outcome": "modify", "created_at": datetime.now().isoformat(),
        })

    nouvelle_confiance = appliquer_feedback(d["rule_id"], "modify" if modifie else body.outcome) if d.get("rule_id") else None

    return {"status": status_map[body.outcome], "nouvelle_confiance": nouvelle_confiance}


@router.post("/{rec_id}/decision-secteur")
def valider_chef_secteur(rec_id: str, body: DecisionGestionnaire, user: dict = Depends(require_roles("chef_secteur"))):
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable")
    if d["status"] != "attente_chef_secteur":
        raise HTTPException(409, "Ce dossier n'est pas en attente de validation par un chef de secteur.")
    if body.outcome not in ("accept", "reject"):
        raise HTTPException(400, "outcome invalide")

    status_map = {"accept": "attente_chef_subdivision", "reject": "rejetee"}
    col_reclamations.update_one({"_id": rec_id}, {"$set": {
        "status": status_map[body.outcome], "valide_par_chef_secteur": user["username"],
    }})

    modifie = body.outcome == "accept" and d.get("rule_id") and (
        d.get("decision") != d.get("decision_original") or d.get("rapport") != d.get("rapport_original")
    )
    if modifie:
        col_corrections.insert_one({
            "rule_id": d["rule_id"], "tax": d["tax"], "motif": d["motif"],
            "texte_original": d.get("decision_original", ""), "texte_corrige": d.get("decision", ""),
            "outcome": "modify", "created_at": datetime.now().isoformat(), "niveau": "chef_secteur",
        })

    return {"status": status_map[body.outcome]}


@router.post("/{rec_id}/decision-subdivision")
def valider_chef_subdivision(rec_id: str, body: DecisionGestionnaire, user: dict = Depends(require_roles("chef_subdivision"))):
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable")
    if d["status"] != "attente_chef_subdivision":
        raise HTTPException(409, "Ce dossier n'est pas en attente de validation par un chef de subdivision.")
    if body.outcome not in ("accept", "reject"):
        raise HTTPException(400, "outcome invalide")

    status_map = {"accept": "validee_finale", "reject": "rejetee"}
    col_reclamations.update_one({"_id": rec_id}, {"$set": {
        "status": status_map[body.outcome], "valide_par_chef_subdivision": user["username"],
    }})

    modifie = body.outcome == "accept" and d.get("rule_id") and (
        d.get("decision") != d.get("decision_original") or d.get("rapport") != d.get("rapport_original")
    )
    if modifie:
        col_corrections.insert_one({
            "rule_id": d["rule_id"], "tax": d["tax"], "motif": d["motif"],
            "texte_original": d.get("decision_original", ""), "texte_corrige": d.get("decision", ""),
            "outcome": "modify", "created_at": datetime.now().isoformat(), "niveau": "chef_subdivision",
        })

    email_envoye = False
    if status_map[body.outcome] == "validee_finale":
        email_envoye = envoyer_email_decision(
            destinataire=d.get("email"), contribuable=d["contrib"], rec_id=rec_id,
            cle_verification=d["cle_verification"], decision=d.get("decision", ""), montant_degreve=d.get("montant_degreve"),
        )
        col_reclamations.update_one({"_id": rec_id}, {"$set": {"email_envoye": email_envoye}})

    return {"status": status_map[body.outcome], "email_envoye": email_envoye}


# ---------- portail SIT : suivi, accusé de lecture, choix du gestionnaire ----------

FINAL_STATUSES = ("validee_finale", "rejetee")


@router.get("/suivi/{rec_id}")
def suivre_reclamation(rec_id: str, ifn: str | None = None, cle: str | None = None):
    """Endpoint public destiné au portail SIT : ne renvoie que ce que le
    contribuable a le droit de voir. Le statut est toujours visible avec la
    seule référence ; la décision et le montant ne sont révélés qu'une fois
    le dossier au statut final ET si la clé de vérification (envoyée par
    e-mail) est fournie et correcte."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Aucune réclamation ne correspond à cette référence.")
    if ifn and d.get("ifn") != ifn:
        raise HTTPException(404, "Aucune réclamation ne correspond à cette référence.")

    est_final = d["status"] in FINAL_STATUSES
    cle_ok = cle is not None and cle == d.get("cle_verification")
    peut_voir_decision = est_final and cle_ok

    return {
        "id": d["_id"],
        "contrib": d["contrib"],
        "tax": d["tax"],
        "motif": d["motif"],
        "montant": d["montant"],
        "status": d["status"],
        "montant_degreve": d.get("montant_degreve") if peut_voir_decision else None,
        "decision": d.get("decision") if peut_voir_decision else None,
        "decision_disponible_mais_cle_requise": est_final and not cle_ok,
        "gestionnaire_choisi": d.get("gestionnaire_choisi"),
        "created_at": d["created_at"],
    }


@router.post("/{rec_id}/lu")
def marquer_lu(rec_id: str, cle: str):
    """Accusé de lecture : appelé par le portail SIT dès que le contribuable
    affiche la décision finale. Nécessite la clé de vérification, comme le
    reste des actions contribuable."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d or cle != d.get("cle_verification"):
        raise HTTPException(404, "Réclamation introuvable ou clé incorrecte.")
    if not d.get("lu_par_contribuable"):
        col_reclamations.update_one({"_id": rec_id}, {"$set": {
            "lu_par_contribuable": True, "date_lecture": datetime.now().isoformat(),
        }})
    return {"lu": True}


@router.get("/{rec_id}")
def obtenir_reclamation(rec_id: str, _user: dict = Depends(get_current_user)):
    """Réservé aux comptes internes désormais (gestionnaire/chefs) — la vue
    complète, contrairement à /suivi qui reste la seule route publique."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable")
    return sans_id_mongo(d)
