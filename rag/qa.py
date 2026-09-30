"""Retrieval-augmented Q&A over receipts.

Design choice (the interview point): an LLM must not do the arithmetic.
  1. parse the question into (payer, currency, window) -- deterministic parser
  2. compute the exact total from structured rows (the source of truth)
  3. retrieve the most relevant receipts by embedding similarity as citations
  4. the LLM only phrases the answer from FACTS + citations; a guard rejects any
     answer that does not contain the computed figure and falls back to a template.
"""
import math
import re
from datetime import date, timedelta
from decimal import Decimal


def receipt_text(r):
    return (f"{r['payer']} paid {r['amount']} {r['currency']} at {r['merchant']} "
            f"on {r['ts'].date().isoformat()} receipt {r['receipt_id']}")


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / ((math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1)


class ReceiptIndex:
    def __init__(self, client, rows):
        self.client, self.rows = client, rows
        self.vectors = client.embed([receipt_text(r) for r in rows])

    def search(self, query, k=5, where=None):
        qv = self.client.embed([query])[0]
        cands = [(cosine(qv, v), r) for v, r in zip(self.vectors, self.rows) if where is None or where(r)]
        return [r for _, r in sorted(cands, key=lambda x: -x[0])[:k]]


def parse_question(q, as_of):
    payer = re.search(r"(payer_\d{3})", q)
    cur = re.search(r"\b(INR|USD|EUR|GBP)\b", q.upper())
    if "last week" in q.lower():
        start, end = as_of - timedelta(days=7), as_of - timedelta(days=1)
    elif m := re.search(r"on (\d{4}-\d{2}-\d{2})", q):
        start = end = date.fromisoformat(m.group(1))
    else:
        start, end = date.min, as_of
    return {"payer": payer and payer.group(1), "currency": cur and cur.group(1), "start": start, "end": end}


SYSTEM = ("You answer questions about payment receipts. Use ONLY the FACTS and receipts given. "
          "Repeat the total exactly as written in FACTS. One sentence.")


def answer(index, question, as_of):
    q = parse_question(question, as_of)
    if not q["payer"]:
        return {"answer": "Please name a payer (e.g. payer_012).", "total": None, "citations": []}

    def match(r):
        return (r["payer"] == q["payer"] and (q["currency"] is None or r["currency"] == q["currency"])
                and q["start"] <= r["ts"].date() <= q["end"])

    hits = [r for r in index.rows if match(r)]
    total = sum((Decimal(r["amount"]) for r in hits), Decimal("0")).quantize(Decimal("0.01"))
    cur = q["currency"] or "mixed currencies"
    facts = (f"{q['payer']} spent {total} {cur} across {len(hits)} receipts "
             f"between {q['start']} and {q['end']}.")
    cites = index.search(question, k=5, where=match)
    ctx = "\n".join(receipt_text(r) for r in cites)
    text = index.client.chat(SYSTEM, f"QUESTION: {question}\nRECEIPTS:\n{ctx}\nFACTS: {facts}")
    grounded = str(total) in text
    return {"answer": text if grounded else facts, "grounded_llm_answer": grounded, "total": total,
            "n_receipts": len(hits), "citations": [r["receipt_id"] for r in cites], "parsed": q}
