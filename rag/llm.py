"""OpenAI-compatible client (works against Ollama's /v1 API) plus a deterministic stub.

The stub lets every test run offline and reproducibly; the real client is the
same interface, so swapping is config-only (LLM_BASE_URL / LLM_MODEL / EMBED_MODEL).
"""
import hashlib
import math
import os
import re

import requests


class OpenAICompatibleClient:
    def __init__(self, base_url=None, chat_model=None, embed_model=None, timeout=120):
        self.base = (base_url or os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
        self.chat_model = chat_model or os.environ.get("LLM_MODEL", "qwen2.5:0.5b")
        self.embed_model = embed_model or os.environ.get("EMBED_MODEL", "nomic-embed-text")
        self.timeout = timeout

    def embed(self, texts):
        r = requests.post(f"{self.base}/embeddings", json={"model": self.embed_model, "input": texts},
                          timeout=self.timeout)
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]

    def chat(self, system, user):
        r = requests.post(f"{self.base}/chat/completions", timeout=self.timeout, json={
            "model": self.chat_model, "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class StubClient:
    """Deterministic: hashed token/trigram bag-of-features embeddings; chat echoes the FACTS line."""
    dims = 256

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * self.dims
            toks = re.findall(r"[a-z0-9_.]+", t.lower())
            feats = toks + [tok[i:i + 3] for tok in toks for i in range(max(1, len(tok) - 2))]
            for f in feats:
                h = int(hashlib.md5(f.encode()).hexdigest(), 16)
                v[h % self.dims] += 1.0 if (h >> 8) % 2 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out

    def chat(self, system, user):
        facts = re.search(r"FACTS: (.*)", user)
        return facts.group(1) if facts else "I don't know."
