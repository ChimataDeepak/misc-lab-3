# LEARN: LLM / RAG (retrieval-augmented generation)

## What
Answer a question with an LLM, but ground it: retrieve relevant records, hand them to the model as context, and check
the answer. Here the question is "how much did payer_055 spend in EUR last week?".

## Why it exists
An LLM alone doesn't know your data and is bad at arithmetic. RAG gives it the data; this lab goes further and never
lets it compute the money figure.

## How it works
```
question --parse_question (regex)--> {payer, currency, start, end}
         --filter rows + Decimal sum--> FACTS: "payer_055 spent 533.20 EUR across 14 receipts ..."
         --embed(question), cosine top-5 among matching rows--> citations
         --chat(SYSTEM, question + citations + FACTS)--> sentence
         --guard: str(total) in sentence ?  sentence : FACTS
```

## Where in this repo
- Parser: `rag/qa.py:36-45`.
- Exact total and facts: `rag/qa.py:58-65`.
- Retrieval: `rag/qa.py:21-33` (cosine over in-memory vectors).
- Guard: `rag/qa.py:68-71`.
- Clients: `rag/llm.py:14-32` (OpenAI-compatible, Ollama `/v1`), `rag/llm.py:35-54` (deterministic stub).

## How it's verified
- `pytest -q tests/test_rag.py`: 6 passed, 1 skipped (Ollama) on 2026-09-30. `test_guard_falls_back_when_llm_hallucinates`
  (line 55) uses a client that answers "1,000,000 EUR" and checks the fallback.
- Real model: `RUN_OLLAMA=1 pytest -q -s tests/test_rag.py -k ollama` with `qwen2.5:0.5b` + `nomic-embed-text` in
  Docker, 1 passed; it failed once on a cold model and passed on rerun (RUN-RESULTS.md).

Honest limits: the parser only knows `payer_NNN`, a currency code, "last week" and "on YYYY-MM-DD"; no vector database;
the guard checks the figure appears, not that the sentence is otherwise correct.

## Interview Q&A
- **Q: How do you stop hallucinated numbers?** Compute them in code, pass them as facts, and validate the output contains
  them (or return structured output and render it yourself).
- **Q: Why embeddings at all if the filter is exact?** Here they only rank citations; in free-text search (merchant
  descriptions, dispute notes) they find matches a keyword filter misses.
- **Q: How would you scale retrieval?** A vector index (pgvector, FAISS, OpenSearch k-NN) with metadata filters, plus
  chunking for long documents.
- **Q: How do you test LLM code?** A deterministic stub for unit tests, a small labelled eval set for the real model,
  temperature 0.

## Try it yourself
1. Support "in September" in `parse_question` and add a test.
2. Store the stub vectors in Postgres with pgvector and replace the Python cosine loop with an `ORDER BY embedding <=> q`.
3. Make the guard also check the receipt count appears in the answer.
