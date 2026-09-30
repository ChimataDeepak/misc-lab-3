"""FastAPI scoring service. POST /score with pre-computed features -> fraud probability."""
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ml.fraud import FEATURES, load

app = FastAPI(title="receipt-fraud-scorer")
_bundle = {}


class ScoreRequest(BaseModel):
    amount_inr: float = Field(gt=0)
    hour: int = Field(ge=0, le=23)
    foreign_currency: bool
    burst_10min: int = Field(ge=0)
    amount_vs_median: float = Field(ge=0)


def model():
    if "m" not in _bundle:
        path = os.environ.get("FRAUD_MODEL", "artifacts/fraud_model.joblib")
        if not os.path.exists(path):
            raise HTTPException(503, "model not trained")
        _bundle["m"] = load(path)["model"]
    return _bundle["m"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/score")
def score(req: ScoreRequest, threshold: float = 0.5):
    import math
    x = [[math.log1p(req.amount_inr), req.hour, int(1 <= req.hour <= 4), int(req.foreign_currency),
          req.burst_10min, req.amount_vs_median]]
    p = float(model().predict_proba(x)[0, 1])
    return {"fraud_probability": round(p, 4), "flag": p >= threshold, "features": FEATURES}
