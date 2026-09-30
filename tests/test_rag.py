import os
from datetime import date
from decimal import Decimal
import pytest

from receipts.generate import generate
from receipts.etl import transform
from rag.llm import StubClient, OpenAICompatibleClient
from rag.qa import ReceiptIndex, answer, parse_question

AS_OF = date(2026, 9, 22)


@pytest.fixture(scope="module")
def clean():
    return transform(generate())[0]


@pytest.fixture(scope="module")
def index(clean):
    return ReceiptIndex(StubClient(), clean)


def expected_total(clean, payer, cur, start, end):
    return sum((r["amount"] for r in clean if r["payer"] == payer and r["currency"] == cur
                and start <= r["ts"].date() <= end), Decimal("0")).quantize(Decimal("0.01"))


def test_parse_last_week():
    q = parse_question("How much did payer_007 spend in EUR last week?", AS_OF)
    assert q == {"payer": "payer_007", "currency": "EUR", "start": date(2026, 9, 15), "end": date(2026, 9, 21)}


def test_stub_embeddings_are_deterministic_and_normalised():
    a, b = StubClient().embed(["payer_001 paid 10 EUR", "payer_001 paid 10 EUR"])
    assert a == b and abs(sum(x * x for x in a) - 1) < 1e-9


def test_retrieval_prefers_matching_receipt(index, clean):
    target = clean[100]
    from rag.qa import receipt_text
    assert index.search(receipt_text(target), k=1)[0]["receipt_id"] == target["receipt_id"]


def test_answer_total_is_computed_not_generated(index, clean):
    # pick a payer who actually has EUR receipts last week
    payer = next(r["payer"] for r in clean if r["currency"] == "EUR" and date(2026, 9, 15) <= r["ts"].date() <= date(2026, 9, 21))
    res = answer(index, f"How much did {payer} spend in EUR last week?", AS_OF)
    assert res["total"] == expected_total(clean, payer, "EUR", date(2026, 9, 15), date(2026, 9, 21))
    assert str(res["total"]) in res["answer"] and res["grounded_llm_answer"]
    ids = {r["receipt_id"] for r in clean}
    assert res["citations"] and set(res["citations"]) <= ids


def test_guard_falls_back_when_llm_hallucinates(index, clean):
    class Liar(StubClient):
        def chat(self, system, user):
            return "They spent 1,000,000 EUR."
    idx = ReceiptIndex(Liar(), clean[:200])
    payer = clean[0]["payer"]
    res = answer(idx, f"how much did {payer} spend?", AS_OF)
    assert not res["grounded_llm_answer"] and "1,000,000" not in res["answer"]


def test_requires_payer(index):
    assert answer(index, "how much was spent last week?", AS_OF)["total"] is None


@pytest.mark.skipif(not os.environ.get("RUN_OLLAMA"), reason="set RUN_OLLAMA=1 with Ollama on :11434")
def test_real_ollama_end_to_end(clean):
    client = OpenAICompatibleClient()
    lw = [r for r in clean if date(2026, 9, 15) <= r["ts"].date() <= date(2026, 9, 21)]
    payer, cur = lw[0]["payer"], lw[0]["currency"]
    subset = [r for r in clean if r["payer"] == payer]
    idx = ReceiptIndex(client, subset)
    res = answer(idx, f"How much did {payer} spend in {cur} last week?", AS_OF)
    assert res["n_receipts"] > 0 and res["total"] > 0
    print("OLLAMA", res["answer"], "| grounded:", res["grounded_llm_answer"], "| total:", res["total"])
    assert res["total"] is not None and len(idx.vectors[0]) > 100
    assert str(res["total"]) in res["answer"]  # either the LLM kept the figure or the guard substituted it
