from fastapi import APIRouter, Depends, Query

from .. import predictions as pred
from .. import saisonnalite
from ..models import PredictionOutcomeRequest, PredictionVolumeRequest
from ..rules_engine import compute_learning_curve
from ..security import get_current_user

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("/volume")
def prevision_volume(body: PredictionVolumeRequest, _user: dict = Depends(get_current_user)):
    return pred.predict_volume(body.tax, body.horizon_jours)


@router.get("/charge")
def charge_a_venir(
    tax: str | None = Query(None, pattern="^(IS|IR|TVA)$"),
    horizon_jours: int = Query(28, ge=7, le=90),
    _user: dict = Depends(get_current_user),
):
    """Charge à venir estimée sur l'historique réel des dépôts (données de la base)."""
    return pred.charge_prevue(tax, horizon_jours)


@router.get("/saisonnalite")
def prevision_saisonniere(
    tax: str = Query("TVA", pattern="^(IS|IR|TVA)$"),
    horizon: int = Query(6, ge=3, le=12),
    _user: dict = Depends(get_current_user),
):
    """Volumes mensuels attendus : baseline saisonnier + SARIMAX sur une série SIMULÉE (pilier Séries temporelles)."""
    return saisonnalite.previsions_saisonnieres(tax, horizon)


@router.post("/outcome")
def prediction_issue(body: PredictionOutcomeRequest, _user: dict = Depends(get_current_user)):
    return pred.predict_outcome(body.tax, body.motif, body.montant, body.date_mer, body.date_reclam)


@router.get("/learning-curve/{rule_id}")
def courbe_apprentissage(rule_id: str, _user: dict = Depends(get_current_user)):
    return {"rule_id": rule_id, "courbe": compute_learning_curve(rule_id)}
