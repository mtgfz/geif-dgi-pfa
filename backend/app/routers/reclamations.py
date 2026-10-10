"""
Réclamations — API du portail public (SIT) et de l'application interne.

Circuit (voir constants.py / workflow.py) :
  nouvelle ──traiter──▶ en_traitement ──/decision──▶ envoyee_chef_service
        ▲                     ▲                              │ /decision-service
        │                     └──── retournee ◀──(retour)────┤
        │                                                    ▼
        └────────────────────────────────── envoyee_chef_subdivision
                                                             │ /decision-subdivision
                                                             ▼
                                            decision_envoyee (= Historique)

Public (aucune connexion)  : POST /reclamations, POST /{id}/documents (clé requise),
                             GET /suivi/{id} (clé requise), POST /{id}/lu
Interne (JWT + rôle)        : tout le reste
"""
import base64
import re
import secrets
from datetime import date, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

from ..config import settings
from ..constants import (
    ACCUEIL_PAR_ROLE, CHEF_SERVICE, CHEF_SUBDIVISION, DECISION_ENVOYEE, EN_TRAITEMENT, ENVOYEE_CS,
    ENVOYEE_CSUB, GESTIONNAIRE, NOUVELLE, RETOURNEE, STATUT_EDITABLE_PAR_ROLE, STATUT_LABELS,
    STATUT_LABELS_PUBLIC, STATUTS, TYPES_DECISION,
)
from ..database import col_corrections, col_documents, col_reclamations, col_rules, sans_id_mongo
from ..email_service import envoyer_email_confirmation_depot, envoyer_email_decision
from ..llm import generer_texte_llm, reformuler_texte, texte_repli
from ..models import DecisionGestionnaire, NouvelleReclamation, ReformulationRequest, ValidationChef
from ..ocr import extraire_document
from ..ratelimit import limite
from ..rag import rechercher_articles_cgi
from ..rules_engine import appliquer_feedback, choisir_regle_id, jours_entre
from ..security import get_current_user, require_roles
from ..workflow import changer_statut, cles_egales, evenement, timeline_publique

router = APIRouter(prefix="/reclamations", tags=["reclamations"])


# ======================================================================
# Utilitaires
# ======================================================================
def _get(rec_id: str) -> dict:
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    return d


def _generer_cle_verification() -> str:
    """Code court, tapable à la main (ex : 7F3K-9QRT), partagé uniquement avec le contribuable."""
    brut = secrets.token_hex(4).upper()
    return f"{brut[:4]}-{brut[4:]}"


def _type_decision(rejet: bool, montant_degreve: float, montant: float) -> str:
    if rejet or montant_degreve <= 0:
        return "Rejet"
    return "Dégrèvement total" if montant_degreve >= montant * 0.999 else "Dégrèvement partiel"


def _item_liste(d: dict) -> dict:
    return {
        "id": d["_id"], "contrib": d["contrib"], "ifn": d["ifn"], "tax": d["tax"], "motif": d["motif"],
        "montant": d["montant"], "montant_degreve": d.get("montant_degreve"),
        "status": d["status"], "status_label": STATUT_LABELS.get(d["status"], d["status"]),
        "type_decision": d.get("type_decision"), "commentaire_retour": d.get("commentaire_retour"),
        "created_at": d["created_at"], "closed_at": d.get("closed_at"),
    }


def _choisir_regle_avec_rag(tax: str, motif: str, delai_jours: int):
    """Comme rules_engine.choisir_regle_id, mais enrichit la règle avec les articles
    réels retrouvés par le RAG sur le CGI. Retourne (rid, regle, articles_top_k)."""
    rid = choisir_regle_id(tax, motif, delai_jours)
    if not rid:
        return None, None, []
    regle = dict(col_rules.find_one({"_id": rid}))
    requete_rag = "délai de réclamation six mois mise en recouvrement" if delai_jours > 180 else motif

    articles = rechercher_articles_cgi(requete_rag, k=4)
    if articles:
        meilleur = articles[0]
        regle["article"] = meilleur["article"]
        regle["resume_legal"] = meilleur["texte"][:500].replace("\n", " ").strip()
        regle["retrieval_score"] = meilleur["score"]
        regle["retrieval_page"] = meilleur["page"]
    else:
        regle["retrieval_score"] = 0
        regle["retrieval_page"] = None
    return rid, regle, articles


def _peut_editer(d: dict, user: dict) -> None:
    attendu = STATUT_EDITABLE_PAR_ROLE.get(user["role"])
    if d["status"] != attendu:
        raise HTTPException(409, "Ce dossier n'est pas modifiable par votre rôle dans son état actuel.")


def _journaliser_correction(d: dict, niveau: str, outcome: str) -> bool:
    """Journalise une correction humaine du texte généré (exemple pour le LLM),
    une seule fois par version : si le texte n'a pas changé depuis la dernière
    correction journalisée, rien n'est ajouté."""
    if not d.get("rule_id"):
        return False
    version = d.get("version_journalisee") or {
        "rapport": d.get("rapport_original"), "decision": d.get("decision_original"),
    }
    if d.get("rapport") == version["rapport"] and d.get("decision") == version["decision"]:
        return False
    col_corrections.insert_one({
        "rule_id": d["rule_id"], "tax": d["tax"], "motif": d["motif"],
        "texte_original": version["decision"] or "", "texte_corrige": d.get("decision", ""),
        "outcome": outcome, "niveau": niveau, "created_at": datetime.now().isoformat(),
    })
    col_reclamations.update_one(
        {"_id": d["_id"]},
        {"$set": {"version_journalisee": {"rapport": d.get("rapport"), "decision": d.get("decision")}}},
    )
    return True


# ======================================================================
# PUBLIC — dépôt, pièces, suivi
# ======================================================================
@router.post("", dependencies=[Depends(limite("depot", 20, 3600))])
def creer_reclamation(r: NouvelleReclamation):
    if date.fromisoformat(r.date_reclam) < date.fromisoformat(r.date_mer):
        raise HTTPException(422, "La date de réclamation ne peut pas précéder la date de mise en recouvrement.")

    rid = "REC-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    maintenant = datetime.now().isoformat()
    doc = {
        "_id": rid, "id": rid,
        "contrib": r.contrib.strip(), "ifn": r.ifn.strip(), "tax": r.tax, "motif": r.motif.strip(),
        "montant": r.montant, "date_mer": r.date_mer, "date_reclam": r.date_reclam,
        "email": r.email, "telephone": r.telephone,
        "cle_verification": _generer_cle_verification(),
        "status": NOUVELLE, "rule_id": None, "article": None, "montant_degreve": None, "type_decision": None,
        "rapport": None, "decision": None, "source_texte": None, "articles_rag": None,
        "retrieval_score": None, "retrieval_page": None,
        "commentaire_retour": None,
        "gestionnaire_choisi": None,
        "lu_par_contribuable": False, "date_lecture": None,
        "email_envoye": False, "email_confirmation_envoye": False,
        "created_at": maintenant, "closed_at": None,
        "historique": [evenement(None, NOUVELLE, "contribuable", "contribuable", "Réclamation déposée via le portail.")],
    }
    col_reclamations.insert_one(doc)

    # Ne bloque jamais la réponse : si SMTP échoue, la clé reste affichée à l'écran.
    confirmation = envoyer_email_confirmation_depot(
        destinataire=r.email, contribuable=r.contrib, rec_id=rid, cle_verification=doc["cle_verification"],
    )
    if confirmation:
        col_reclamations.update_one({"_id": rid}, {"$set": {"email_confirmation_envoye": True}})
    return {"id": rid, "cle_verification": doc["cle_verification"], "email_confirmation_envoye": confirmation}


@router.post("/{rec_id}/documents", dependencies=[Depends(limite("documents", 20, 3600))])
async def deposer_documents(
    rec_id: str,
    cle: str = Form(..., description="Clé de vérification reçue au dépôt"),
    demande_degrevement: UploadFile = File(..., description="Document obligatoire — demande de dégrèvement"),
    description_demande: str = Form(..., max_length=settings.DOCUMENT_DESCRIPTION_MAX),
    documents_optionnels: list[UploadFile] = File(default=[]),
    descriptions_optionnelles: list[str] = Form(default=[]),
):
    """Reçoit la demande de dégrèvement (obligatoire) et jusqu'à 5 pièces optionnelles.
    Chaque fichier est lu immédiatement (OCR / couche texte PDF) et ses champs sont extraits."""
    d = _get(rec_id)
    if not cles_egales(cle, d.get("cle_verification")):
        raise HTTPException(403, "Clé de vérification incorrecte.")
    if col_documents.count_documents({"reclamation_id": rec_id}) > 0:
        raise HTTPException(409, "Les documents de ce dossier ont déjà été déposés.")
    if len(documents_optionnels) > settings.DOCUMENT_MAX_OPTIONNELS:
        raise HTTPException(400, f"Maximum {settings.DOCUMENT_MAX_OPTIONNELS} documents optionnels.")
    if len(descriptions_optionnelles) != len(documents_optionnels):
        raise HTTPException(400, "Chaque document optionnel doit avoir exactement une description.")

    tous = [(demande_degrevement, description_demande, True)] + [
        (f, desc, False) for f, desc in zip(documents_optionnels, descriptions_optionnelles)
    ]

    # 1) validation de TOUS les fichiers avant d'enregistrer quoi que ce soit
    lus = []
    for fichier, description, obligatoire in tous:
        if fichier.content_type not in settings.DOCUMENT_TYPES_AUTORISES:
            raise HTTPException(400, f"Format non autorisé pour « {fichier.filename} » (PDF, PNG ou JPG uniquement).")
        contenu = await fichier.read()
        if len(contenu) > settings.DOCUMENT_TAILLE_MAX_MO * 1024 * 1024:
            raise HTTPException(400, f"« {fichier.filename} » dépasse {settings.DOCUMENT_TAILLE_MAX_MO} Mo.")
        if not description or len(description) > settings.DOCUMENT_DESCRIPTION_MAX:
            raise HTTPException(400, f"Description invalide pour « {fichier.filename} » (max {settings.DOCUMENT_DESCRIPTION_MAX} caractères).")
        lus.append((fichier, description, obligatoire, contenu))

    # 2) lecture + enregistrement
    enregistres = []
    for fichier, description, obligatoire, contenu in lus:
        lecture = extraire_document(contenu, fichier.content_type, fichier.filename)
        col_documents.insert_one({
            "reclamation_id": rec_id,
            "filename": fichier.filename, "content_type": fichier.content_type,
            "description": description, "obligatoire": obligatoire, "taille": len(contenu),
            "contenu_b64": base64.b64encode(contenu).decode(),
            "texte_ocr": lecture["texte"], "ocr_ok": lecture["ok"], "ocr_methode": lecture["methode"],
            "ocr_erreur": lecture["erreur"], "champs_ocr": lecture["champs"],
            "uploaded_at": datetime.now().isoformat(),
        })
        enregistres.append({
            "filename": fichier.filename, "description": description,
            "ocr_ok": lecture["ok"], "ocr_methode": lecture["methode"], "ocr_erreur": lecture["erreur"],
        })
    return {"reclamation_id": rec_id, "documents_enregistres": enregistres}


@router.get("/suivi/{rec_id}", dependencies=[Depends(limite("suivi", 15, 600))])
def suivre_reclamation(rec_id: str, cle: str = Query(..., description="Code reçu au dépôt")):
    """Page Suivi du contribuable : référence + code obligatoires. Renvoie la frise
    de statuts (sans détail interne) et, une fois la décision envoyée, la décision."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d or not cles_egales(cle, d.get("cle_verification")):
        # même message dans les deux cas : on ne révèle pas si la référence existe
        raise HTTPException(404, "Référence ou code incorrect.")

    termine = d["status"] == DECISION_ENVOYEE
    frise = timeline_publique(d)
    return {
        "id": d["_id"], "contrib": d["contrib"], "tax": d["tax"], "motif": d["motif"], "montant": d["montant"],
        "status": d["status"], "status_label": STATUT_LABELS_PUBLIC[d["status"]],
        "etapes": frise["etapes"], "evenements": frise["evenements"],
        "decision_disponible": termine,
        "decision": d.get("decision") if termine else None,
        "type_decision": d.get("type_decision") if termine else None,
        "montant_degreve": d.get("montant_degreve") if termine else None,
        "date_decision": d.get("closed_at") if termine else None,
        "gestionnaire_choisi": d.get("gestionnaire_choisi"),
        "created_at": d["created_at"],
    }


@router.post("/{rec_id}/lu", dependencies=[Depends(limite("lu", 30, 600))])
def marquer_lu(rec_id: str, cle: str):
    """Accusé de lecture : appelé par le portail dès que le contribuable affiche la décision."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d or not cles_egales(cle, d.get("cle_verification")):
        raise HTTPException(404, "Réclamation introuvable ou clé incorrecte.")
    if d["status"] != DECISION_ENVOYEE:
        raise HTTPException(409, "Aucune décision n'a encore été envoyée.")
    if not d.get("lu_par_contribuable"):
        col_reclamations.update_one({"_id": rec_id}, {"$set": {
            "lu_par_contribuable": True, "date_lecture": datetime.now().isoformat(),
        }})
    return {"lu": True}


# ======================================================================
# INTERNE — listes, compteurs, détail, pièces
# ======================================================================
@router.get("")
def lister_reclamations(
    scope: str = Query("accueil", pattern="^(accueil|historique|all)$"),
    q: str | None = Query(None, description="Recherche : référence, raison sociale, IF, motif, e-mail"),
    tax: str | None = None,
    status: str | None = Query(None, description="Un ou plusieurs statuts séparés par des virgules"),
    type_decision: str | None = None,
    date_from: str | None = Query(None, description="AAAA-MM-JJ"),
    date_to: str | None = Query(None, description="AAAA-MM-JJ"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """
    scope=accueil    -> file d'attente du rôle connecté (jamais les dossiers terminés)
    scope=historique -> dossiers dont la décision a été envoyée (recherche complète)
    scope=all        -> tout (dashboard)
    """
    conditions = []
    if scope == "accueil":
        conditions.append({"status": {"$in": list(ACCUEIL_PAR_ROLE.get(user["role"], ()))}})
    elif scope == "historique":
        conditions.append({"status": DECISION_ENVOYEE})
    if status:
        conditions.append({"status": {"$in": [s for s in status.split(",") if s in STATUTS]}})
    if tax:
        conditions.append({"tax": tax})
    if type_decision:
        conditions.append({"type_decision": type_decision})
    if q and q.strip():
        motif = re.escape(q.strip())
        conditions.append({"$or": [
            {champ: {"$regex": motif, "$options": "i"}} for champ in ("_id", "contrib", "ifn", "motif", "email")
        ]})
    champ_date = "closed_at" if scope == "historique" else "created_at"
    if date_from:
        conditions.append({champ_date: {"$gte": date_from}})
    if date_to:
        conditions.append({champ_date: {"$lte": date_to + "T23:59:59.999999"}})

    filtre = {"$and": conditions} if conditions else {}
    total = col_reclamations.count_documents(filtre)
    tri = [("closed_at", -1)] if scope == "historique" else [("created_at", -1)]
    rows = col_reclamations.find(filtre).sort(tri).skip(skip).limit(limit)
    return {"items": [_item_liste(r) for r in rows], "total": total}


@router.get("/compteurs")
def compteurs(user: dict = Depends(get_current_user)):
    """Compteurs pour la barre de navigation (badges)."""
    par_statut = {s: col_reclamations.count_documents({"status": s}) for s in STATUTS}
    return {
        "accueil": sum(par_statut[s] for s in ACCUEIL_PAR_ROLE.get(user["role"], ())),
        "historique": par_statut[DECISION_ENVOYEE],
        "total": sum(par_statut.values()),
        "par_statut": par_statut,
    }


@router.get("/{rec_id}")
def obtenir_reclamation(rec_id: str, _user: dict = Depends(get_current_user)):
    d = sans_id_mongo(_get(rec_id))
    d["status_label"] = STATUT_LABELS.get(d["status"], d["status"])
    try:
        d["delai_jours"] = jours_entre(d["date_mer"], d["date_reclam"])
    except Exception:
        d["delai_jours"] = None
    return d


@router.get("/{rec_id}/documents")
def lister_documents(rec_id: str, _user: dict = Depends(get_current_user)):
    """Pièces jointes : métadonnées, texte lu, champs extraits (sans le contenu binaire)."""
    return [
        {
            "id": str(r["_id"]), "filename": r["filename"], "description": r["description"],
            "obligatoire": r["obligatoire"], "content_type": r["content_type"], "taille": r.get("taille"),
            "texte_ocr": r.get("texte_ocr", ""),
            "ocr_ok": r.get("ocr_ok", not str(r.get("texte_ocr", "")).startswith("(")),
            "ocr_methode": r.get("ocr_methode"), "ocr_erreur": r.get("ocr_erreur"),
            "champs_ocr": r.get("champs_ocr") or {}, "uploaded_at": r["uploaded_at"],
        }
        for r in col_documents.find({"reclamation_id": rec_id})
    ]


@router.get("/{rec_id}/documents/{doc_id}/fichier")
def telecharger_document(rec_id: str, doc_id: str, _user: dict = Depends(get_current_user)):
    """Contenu du fichier original (pour que les chefs LISENT les pièces dans l'application)."""
    try:
        oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(404, "Document introuvable.")
    r = col_documents.find_one({"_id": oid, "reclamation_id": rec_id})
    if not r or not r.get("contenu_b64"):
        raise HTTPException(404, "Document introuvable.")
    nom = re.sub(r'[^\w.\- ]', "_", r["filename"])
    return Response(
        content=base64.b64decode(r["contenu_b64"]), media_type=r["content_type"],
        headers={"Content-Disposition": f'inline; filename="{nom}"'},
    )


# ======================================================================
# GESTIONNAIRE — « Traiter la réclamation »
# ======================================================================
@router.post("/{rec_id}/traiter")
def traiter_reclamation(
    rec_id: str,
    regenerer: bool = Query(False, description="Forcer une nouvelle génération (écrase le texte actuel)"),
    user: dict = Depends(require_roles(GESTIONNAIRE)),
):
    """Passe le dossier « En traitement » et prépare : lecture des pièces (OCR), articles du CGI
    (RAG), rapport d'instruction + décision proposée (LLM). Si le dossier a déjà un texte
    (retour d'un chef, ou page rouverte), on le conserve sauf si regenerer=true."""
    d = _get(rec_id)
    if d["status"] not in (NOUVELLE, EN_TRAITEMENT, RETOURNEE):
        raise HTTPException(409, f"Ce dossier ne peut plus être traité (statut : {STATUT_LABELS.get(d['status'])}).")

    deja_genere = bool(d.get("rapport")) and bool(d.get("decision"))
    if deja_genere and not regenerer:
        if d["status"] != EN_TRAITEMENT:
            d = changer_statut(rec_id, (RETOURNEE,), EN_TRAITEMENT, user["username"], user["role"],
                               "Reprise du traitement après retour.")
        return _reponse_traitement(d)

    delai = jours_entre(d["date_mer"], d["date_reclam"])
    rid, regle, articles = _choisir_regle_avec_rag(d["tax"], d["motif"], delai)
    if not rid:
        raise HTTPException(422, "Aucune règle applicable pour ce type d'impôt.")

    rejet = regle["taux"] == 0.0
    montant_degreve = round(d["montant"] * regle["taux"], 2)

    pieces = list(col_documents.find({"reclamation_id": rec_id}))
    lisibles = [p for p in pieces if p.get("texte_ocr") and p.get("ocr_ok", not str(p["texte_ocr"]).startswith("("))]
    texte_pieces = "\n\n".join(
        f"--- Document « {p['description']} » ({p['filename']}) ---\n{p['texte_ocr']}" for p in lisibles
    )

    llm_text, source = generer_texte_llm(d, regle, rid, montant_degreve, rejet, delai, texte_pieces)
    if llm_text is None:
        llm_text = texte_repli(d, regle, montant_degreve, rejet, delai)
    if "DECISION:" in llm_text:
        rapport, decision = llm_text.split("DECISION:", 1)
        rapport, decision = rapport.replace("RAPPORT:", "").strip(), decision.strip()
    else:
        rapport, decision = llm_text, ""

    extra = {
        "rule_id": rid, "article": regle["article"], "montant_degreve": montant_degreve,
        "type_decision": _type_decision(rejet, montant_degreve, d["montant"]),
        "rapport": rapport, "decision": decision, "rapport_original": rapport, "decision_original": decision,
        "version_journalisee": None, "source_texte": source, "traite_par": user["username"],
        "articles_rag": [
            {"article": a["article"], "page": a["page"], "score": a["score"], "extrait": a["texte"][:600]}
            for a in articles
        ],
        "retrieval_score": regle.get("retrieval_score", 0), "retrieval_page": regle.get("retrieval_page"),
        "commentaire_retour": None,
    }
    if d["status"] == EN_TRAITEMENT:  # régénération : le statut ne change pas
        col_reclamations.update_one({"_id": rec_id}, {
            "$set": extra,
            "$push": {"historique": evenement(EN_TRAITEMENT, EN_TRAITEMENT, user["username"], user["role"], "Texte régénéré.")},
        })
        d = _get(rec_id)
    else:
        d = changer_statut(rec_id, (NOUVELLE, RETOURNEE), EN_TRAITEMENT, user["username"], user["role"],
                           "Traitement lancé (lecture des pièces, RAG sur le CGI, génération).", extra)
    return _reponse_traitement(d, delai, len(lisibles), len(pieces))


def _reponse_traitement(d: dict, delai: int | None = None, nb_lisibles: int | None = None, nb_pieces: int | None = None) -> dict:
    if delai is None:
        delai = jours_entre(d["date_mer"], d["date_reclam"])
    score = d.get("retrieval_score") or 0
    return {
        "status": d["status"], "rule_id": d.get("rule_id"), "article": d.get("article"),
        "montant_degreve": d.get("montant_degreve"), "type_decision": d.get("type_decision"),
        "rapport": d.get("rapport"), "decision": d.get("decision"), "source_texte": d.get("source_texte"),
        "delai_jours": delai, "articles_rag": d.get("articles_rag") or [],
        "retrieval_score": score, "retrieval_faible": score < settings.SEUIL_CONFIANCE_RETRIEVAL,
        "pieces_lisibles": nb_lisibles, "pieces_total": nb_pieces,
    }


@router.post("/{rec_id}/reformuler")
def reformuler(rec_id: str, body: ReformulationRequest, user: dict = Depends(get_current_user)):
    """Assistant IA : réécrit rapport + décision selon une instruction. Ne sauvegarde rien."""
    d = _get(rec_id)
    _peut_editer(d, user)
    resultat = reformuler_texte(d.get("rapport", ""), d.get("decision", ""), body.instruction)
    if not resultat["ok"]:
        raise HTTPException(503, "Assistant IA indisponible pour le moment (clé Groq non configurée ou service injoignable).")
    return resultat


@router.post("/{rec_id}/brouillon")
def sauvegarder_brouillon(rec_id: str, body: DecisionGestionnaire, user: dict = Depends(get_current_user)):
    """Enregistre le rapport / la décision en cours d'édition. N'avance pas le workflow."""
    d = _get(rec_id)
    _peut_editer(d, user)
    updates = {}
    if body.rapport_finale is not None:
        updates["rapport"] = body.rapport_finale
    if body.decision_finale is not None:
        updates["decision"] = body.decision_finale
    if body.type_decision is not None:
        if body.type_decision not in TYPES_DECISION:
            raise HTTPException(422, f"Type de décision invalide (attendu : {', '.join(TYPES_DECISION)}).")
        updates["type_decision"] = body.type_decision
    if not updates:
        raise HTTPException(400, "Rien à enregistrer.")
    col_reclamations.update_one({"_id": rec_id}, {"$set": updates})
    return {"enregistre": True}


# ======================================================================
# CHAÎNE DE VALIDATION
# ======================================================================
# 1) Gestionnaire (/decision) : envoie au Chef de Service. C'est le seul niveau qui
#    nourrit l'apprentissage bayésien (appliquer_feedback) :
#       accept  -> texte envoyé tel quel (ou modifié légèrement : "modify")
#       reject  -> « la proposition de l'IA était fausse, j'ai rédigé la décision moi-même »
#    Dans les deux cas le dossier part au Chef de Service : « reject » n'est PAS une clôture.
# 2) Chef de Service (/decision-service) : valide -> Chef de Subdivision, ou retourne
#    (commentaire obligatoire) -> dossier « Retournée » chez le gestionnaire.
# 3) Chef de Subdivision (/decision-subdivision) : valide -> décision envoyée au
#    contribuable (e-mail + page Suivi) et dossier dans Historique, ou retourne.
@router.post("/{rec_id}/decision")
def valider_reclamation(rec_id: str, body: DecisionGestionnaire, user: dict = Depends(require_roles(GESTIONNAIRE))):
    d = _get(rec_id)
    if d["status"] != EN_TRAITEMENT:
        raise HTTPException(409, f"Envoi impossible : le dossier est au statut « {STATUT_LABELS.get(d['status'], d['status'])} ».")
    if body.outcome not in ("accept", "reject"):
        raise HTTPException(400, "outcome invalide (accept ou reject).")

    # texte éventuellement fourni avec l'envoi
    updates = {}
    if body.rapport_finale is not None:
        updates["rapport"] = body.rapport_finale
    if body.decision_finale is not None:
        updates["decision"] = body.decision_finale
    if body.type_decision is not None:
        if body.type_decision not in TYPES_DECISION:
            raise HTTPException(422, f"Type de décision invalide (attendu : {', '.join(TYPES_DECISION)}).")
        updates["type_decision"] = body.type_decision
    if updates:
        col_reclamations.update_one({"_id": rec_id}, {"$set": updates})
        d = _get(rec_id)

    manquants = [n for n, v in (("rapport d'instruction", d.get("rapport")), ("décision", d.get("decision")),
                                ("type de décision", d.get("type_decision"))) if not (v or "").strip()]
    if manquants:
        raise HTTPException(422, f"Champs obligatoires manquants : {', '.join(manquants)}.")

    modifie = bool(d.get("rule_id")) and (
        d.get("decision") != d.get("decision_original") or d.get("rapport") != d.get("rapport_original")
    )
    outcome_fb = "reject" if body.outcome == "reject" else ("modify" if modifie else "accept")

    changer_statut(rec_id, (EN_TRAITEMENT,), ENVOYEE_CS, user["username"], user["role"],
                   "Validé par le gestionnaire" + (" (proposition IA rejetée, texte rédigé manuellement)" if outcome_fb == "reject" else ""),
                   {"valide_par_gestionnaire": user["username"], "commentaire_retour": None})

    _journaliser_correction(d, GESTIONNAIRE, outcome_fb)
    confiance = appliquer_feedback(d["rule_id"], outcome_fb) if d.get("rule_id") else None
    return {"status": ENVOYEE_CS, "nouvelle_confiance": confiance, "feedback": outcome_fb}


def _traiter_decision_chef(rec_id: str, body: ValidationChef, user: dict, role: str, attendu: str, suivant: str):
    if user["role"] != role:  # défense en profondeur (require_roles est déjà appliqué)
        raise HTTPException(403, "Action non autorisée pour votre rôle.")
    d = _get(rec_id)
    if d["status"] != attendu:
        raise HTTPException(409, f"Ce dossier n'est pas en attente de votre validation (statut : {STATUT_LABELS.get(d['status'], d['status'])}).")

    if body.outcome == "return":
        commentaire = (body.commentaire or "").strip()
        if len(commentaire) < 3:
            raise HTTPException(422, "Un commentaire est obligatoire pour retourner un dossier.")
        changer_statut(rec_id, (attendu,), RETOURNEE, user["username"], user["role"], commentaire,
                       {"commentaire_retour": commentaire, "retourne_par": user["username"]})
        return {"status": RETOURNEE}

    _journaliser_correction(d, role, "modify")
    cle_champ = "valide_par_" + role
    if suivant != DECISION_ENVOYEE:
        changer_statut(rec_id, (attendu,), suivant, user["username"], user["role"],
                       body.commentaire or None, {cle_champ: user["username"]})
        return {"status": suivant}

    # Validation finale : la décision part au contribuable
    now = datetime.now().isoformat()
    d = changer_statut(rec_id, (attendu,), DECISION_ENVOYEE, user["username"], user["role"],
                       "Décision finale envoyée au contribuable.",
                       {cle_champ: user["username"], "closed_at": now, "decision_finale": d.get("decision")})
    email_envoye = envoyer_email_decision(
        destinataire=d.get("email"), contribuable=d["contrib"], rec_id=rec_id,
        cle_verification=d["cle_verification"], decision=d.get("decision", ""), montant_degreve=d.get("montant_degreve"),
    )
    col_reclamations.update_one({"_id": rec_id}, {"$set": {"email_envoye": email_envoye}})
    return {"status": DECISION_ENVOYEE, "email_envoye": email_envoye}


@router.post("/{rec_id}/decision-service")
def valider_chef_service(rec_id: str, body: ValidationChef, user: dict = Depends(require_roles(CHEF_SERVICE))):
    return _traiter_decision_chef(rec_id, body, user, CHEF_SERVICE, ENVOYEE_CS, ENVOYEE_CSUB)


@router.post("/{rec_id}/decision-subdivision")
def valider_chef_subdivision(rec_id: str, body: ValidationChef, user: dict = Depends(require_roles(CHEF_SUBDIVISION))):
    return _traiter_decision_chef(rec_id, body, user, CHEF_SUBDIVISION, ENVOYEE_CSUB, DECISION_ENVOYEE)
