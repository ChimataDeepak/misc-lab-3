import pytest
from fastapi.testclient import TestClient

from receipts.generate import generate
from receipts.etl import transform
from ml import fraud, api


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    model, metrics = fraud.train(transform(generate())[0])
    path = tmp_path_factory.mktemp("m") / "fraud.joblib"
    fraud.save(model, path)
    return path, metrics


def test_metrics_clear_quality_bar(trained):
    _, m = trained
    print("METRICS", m)
    assert m["roc_auc"] >= 0.95 and m["recall"] >= 0.8 and m["precision"] >= 0.7


def test_features_flag_burst_and_foreign():
    X, y, rows = fraud.build_features(transform(generate())[0])
    burst = X[:, fraud.FEATURES.index("burst_10min")]
    assert burst[y == 1].max() >= 4 and burst[y == 0].mean() < 0.2


def test_model_roundtrip(trained):
    path, _ = trained
    assert fraud.load(path)["features"] == fraud.FEATURES


@pytest.fixture
def client(trained, monkeypatch):
    monkeypatch.setenv("FRAUD_MODEL", str(trained[0]))
    api._bundle.clear()
    return TestClient(api.app)


def test_score_endpoint_separates_normal_from_fraud(client):
    normal = client.post("/score", json={"amount_inr": 800, "hour": 13, "foreign_currency": False,
                                         "burst_10min": 0, "amount_vs_median": 1.0}).json()
    fraudy = client.post("/score", json={"amount_inr": 250000, "hour": 2, "foreign_currency": True,
                                         "burst_10min": 0, "amount_vs_median": 60.0}).json()
    assert normal["flag"] is False and fraudy["flag"] is True
    assert fraudy["fraud_probability"] > normal["fraud_probability"]


def test_score_rejects_invalid_input(client):
    assert client.post("/score", json={"amount_inr": -1, "hour": 30, "foreign_currency": False,
                                       "burst_10min": 0, "amount_vs_median": 1}).status_code == 422


def test_503_when_model_missing(monkeypatch):
    monkeypatch.setenv("FRAUD_MODEL", "/nonexistent")
    api._bundle.clear()
    assert TestClient(api.app).get("/health").status_code == 200
    assert TestClient(api.app).post("/score", json={"amount_inr": 1, "hour": 1, "foreign_currency": False,
                                                    "burst_10min": 0, "amount_vs_median": 1}).status_code == 503
