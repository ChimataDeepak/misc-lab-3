"""Fraud classifier on SYNTHETIC receipts (patterns are injected by the generator,
so the metrics measure how well features recover known patterns, not real-world fraud).

Features (all computable at scoring time from the payer's history):
  amount_inr_log, hour, is_night, foreign_currency (not the payer's usual one),
  payer_txn_last_10min (burst), amount_vs_payer_median.
"""
import math
from collections import defaultdict, Counter
from datetime import timedelta

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

FEATURES = ["amount_inr_log", "hour", "is_night", "foreign_currency", "burst_10min", "amount_vs_median"]


def build_features(clean):
    """clean: output of receipts.etl.transform. Returns (X, y, rows_sorted)."""
    rows = sorted(clean, key=lambda r: r["ts"])
    cur_counts = defaultdict(Counter)
    amounts = defaultdict(list)
    recent = defaultdict(list)
    X, y = [], []
    for r in rows:
        p = r["payer"]
        amt = float(r["amount_inr"])
        home = cur_counts[p].most_common(1)[0][0] if cur_counts[p] else r["currency"]
        recent[p] = [t for t in recent[p] if r["ts"] - t <= timedelta(minutes=10)]
        med = float(np.median(amounts[p])) if amounts[p] else amt
        X.append([math.log1p(amt), r["ts"].hour, int(1 <= r["ts"].hour <= 4),
                  int(r["currency"] != home), len(recent[p]), amt / med if med else 1.0])
        y.append(int(r["is_fraud"]))
        cur_counts[p][r["currency"]] += 1
        amounts[p].append(amt)
        recent[p].append(r["ts"])
    return np.array(X), np.array(y), rows


def train(clean, seed=42):
    X, y, _ = build_features(clean)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=seed, stratify=y)
    model = RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced", random_state=seed)
    model.fit(Xtr, ytr)
    proba = model.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)
    metrics = {"n_train": len(ytr), "n_test": len(yte), "fraud_rate": round(float(y.mean()), 4),
               "precision": round(precision_score(yte, pred), 4), "recall": round(recall_score(yte, pred), 4),
               "roc_auc": round(roc_auc_score(yte, proba), 4)}
    return model, metrics


def save(model, path):
    joblib.dump({"model": model, "features": FEATURES}, path)


def load(path):
    return joblib.load(path)


if __name__ == "__main__":
    import json, os, sys
    from receipts.generate import generate
    from receipts.etl import transform
    model, m = train(transform(generate())[0])
    os.makedirs("artifacts", exist_ok=True)
    save(model, "artifacts/fraud_model.joblib")
    print(json.dumps(m))
