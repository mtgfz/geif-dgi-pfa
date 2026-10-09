from fastapi import APIRouter, Depends

from .. import predictions as pred
from ..models import PredictionOutcomeRequest, PredictionVolumeRequest
from ..rules_engine import compute_learning_curve
from ..security import get_current_user

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("/volume")
def prevision_volume(body: PredictionVolumeRequest, _user: dict = Depends(get_current_user)):
    return pred.predict_volume(body.tax, body.horizon_jours)


@router.post("/outcome")
def prediction_issue(body: PredictionOutcomeRequest, _user: dict = Depends(get_current_user)):
    return pred.predict_outcome(body.tax, body.motif, body.montant, body.date_mer, body.date_reclam)


@router.get("/learning-curve/{rule_id}")
def courbe_apprentissage(rule_id: str, _user: dict = Depends(get_current_user)):
    return {"rule_id": rule_id, "courbe": compute_learning_curve(rule_id)}
