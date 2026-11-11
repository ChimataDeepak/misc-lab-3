# LEARN: Machine learning (fraud classifier + FastAPI serving)

## What
A supervised classifier (scikit-learn RandomForest) that scores a receipt's fraud probability from six features, saved
with joblib and served by a FastAPI endpoint.

## Why it exists
Rules catch the fraud you already know about; a model combines weak signals (amount vs usual, burst, foreign currency,
night) into one score a risk team can threshold.

## How it works
```
clean rows sorted by ts --> per payer, using only PAST rows:
   amount_inr_log, hour, is_night (01-04), foreign_currency (!= payer's most common so far),
   burst_10min (payer txns in last 10 min), amount_vs_median (vs payer's past median)
--> stratified 70/30 split --> RandomForest(200 trees, depth 8, class_weight=balanced)
--> precision / recall / ROC-AUC --> artifacts/fraud_model.joblib --> POST /score
```

## Where in this repo
- Features (point-in-time): `ml/fraud.py:21-40`.
- Train + metrics: `ml/fraud.py:43-53` (split at line 45, model at 46).
- Serving: `ml/api.py:12-17` (pydantic bounds), `20-26` (503 without a model), `34-40` (`/score`).
- Injected fraud patterns: `receipts/generate.py:38-54`.

## How it's verified
- `pytest -q tests/test_ml.py`: 6 passed on 2026-09-30 (quality bar, burst feature, model round trip, endpoint,
  422 on bad input, 503 without model).
- `python -m ml.fraud` on 2026-09-30: n_train 2187, n_test 938, precision 0.90, recall 0.9474, ROC-AUC 0.9998.

Honest limits: the data is synthetic and the patterns were injected, so the near-perfect ROC-AUC only shows the features
recover them. The split is random (stratified), not time-based (`ml/fraud.py:45`): features are point-in-time but
test receipts can be older than training receipts. `/score` expects the caller to compute the history features.

## Interview Q&A
- **Q: Why not accuracy?** ~4 % fraud: predicting "never fraud" is 96 % accurate. Report precision (cost of false
  alarms) and recall (fraud caught).
- **Q: What is leakage?** Using information not available at prediction time. Fix: compute features from history only,
  and split train/test by time.
- **Q: How do you pick the threshold?** From the cost of a false positive (blocked customer) vs a missed fraud; `/score`
  takes `threshold` as a query parameter.
- **Q: What changes in production?** A feature store so serving and training compute features the same way, drift
  monitoring, model versioning, shadow deployment.

## Try it yourself
1. Replace `train_test_split` with a time split (first 70 % by `ts` train, rest test) and compare metrics.
2. Print `model.feature_importances_` and drop the weakest feature; does recall change?
3. Add a `/score` test with `threshold=0.9` and explain the precision/recall trade.
