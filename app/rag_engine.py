from __future__ import annotations

import os
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "lab_knowledge")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LLM_URL = os.getenv("CHAT_LLM_URL", os.getenv("LLM_URL", "http://127.0.0.1:8081/v1/chat/completions"))
LLM_MODEL_NAME = os.getenv("CHAT_LLM_MODEL_NAME", os.getenv("LLM_MODEL_NAME", "local-gguf"))


class RagEngine:
    def __init__(self) -> None:
        self.encoder = SentenceTransformer(EMBED_MODEL)
        self.qdrant = QdrantClient(url=QDRANT_URL)

    @staticmethod
    def _build_filter(topic: str | None, corpus: str) -> Filter | None:
        must: list[FieldCondition] = []
        if topic:
            must.append(FieldCondition(key="topic", match=MatchValue(value=topic)))
        if corpus in {"lab", "general"}:
            must.append(FieldCondition(key="corpus", match=MatchValue(value=corpus)))
        return Filter(must=must) if must else None

    def retrieve_context(
        self,
        question: str,
        topic: str | None = None,
        corpus: str = "all",
        limit: int = 8,
    ) -> tuple[str, list[str]]:
        vector = self.encoder.encode(question).tolist()
        points = self.qdrant.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=vector,
            query_filter=self._build_filter(topic, corpus),
            limit=limit,
            with_payload=True,
        )

        contexts: list[str] = []
        sources: list[str] = []
        for p in points:
            payload = p.payload or {}
            text = payload.get("text", "")
            src = payload.get("source", "unknown")
            src_corpus = payload.get("corpus", "lab")
            if text:
                contexts.append(str(text))
                sources.append(f"{src} [{src_corpus}]")

        return "\n\n---\n\n".join(contexts), sources

    async def generate_answer(self, question: str, context: str, corpus: str) -> str:
        system_prompt = (
            "You are an assistant for a battery research and applications lab. "
            "Use provided context. Distinguish lab-specific facts from general literature claims. "
            "If uncertain, say so clearly."
        )

        body: dict[str, Any] = {
            "model": LLM_MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Corpus mode: {corpus}\n\nContext:\n{context}\n\nQuestion:\n{question}",
                },
            ],
            "temperature": 0.2,
            "max_tokens": 700,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(LLM_URL, json=body)
            resp.raise_for_status()
            data = resp.json()

        return data["choices"][0]["message"]["content"].strip()
