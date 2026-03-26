from __future__ import annotations

import hashlib
from pathlib import Path

from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

DATA_DIR = Path("data/knowledge")
COLLECTION = "lab_knowledge"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}


def chunk_text(text: str, chunk_size: int = 1100, overlap: int = 180) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c.strip() for c in chunks if c.strip()]


def stable_id(source: str, idx: int, text: str) -> int:
    digest = hashlib.sha256(f"{source}:{idx}:{text}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def detect_corpus(path: Path) -> str:
    rel_parts = path.relative_to(DATA_DIR).parts
    if not rel_parts:
        return "lab"

    first = rel_parts[0].lower()
    if first in {"general", "public", "literature"}:
        return "general"
    return "lab"


def detect_topic(path: Path, corpus: str) -> str:
    rel_parts = path.relative_to(DATA_DIR).parts

    if corpus == "general":
        if len(rel_parts) >= 2:
            return rel_parts[1].lower()
        return "general"

    if rel_parts:
        first = rel_parts[0].lower()
        if first not in {"_shared", "misc"}:
            return first

    name = path.stem.lower()
    for topic in [
        "about",
        "location",
        "research",
        "education",
        "consulting",
        "pricing",
        "projects",
        "faq",
        "partners",
    ]:
        if topic in name:
            return topic
    return "general"


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages)

    raise ValueError(f"Unsupported file type: {path}")


def iter_knowledge_files() -> list[Path]:
    return sorted(
        p for p in DATA_DIR.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def main() -> None:
    model = SentenceTransformer(EMBED_MODEL)
    qdrant = QdrantClient(url="http://127.0.0.1:6333")

    dim = model.get_sentence_embedding_dimension()
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)

    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    points: list[PointStruct] = []
    files = iter_knowledge_files()

    for file_path in files:
        rel_source = str(file_path.relative_to(DATA_DIR))
        corpus = detect_corpus(file_path)
        topic = detect_topic(file_path, corpus)
        text = extract_text(file_path)
        chunks = chunk_text(text)
        if not chunks:
            continue

        vectors = model.encode(chunks).tolist()
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            points.append(
                PointStruct(
                    id=stable_id(rel_source, i, chunk),
                    vector=vector,
                    payload={
                        "text": chunk,
                        "source": rel_source,
                        "topic": topic,
                        "corpus": corpus,
                        "filetype": file_path.suffix.lower().lstrip("."),
                    },
                )
            )

    if points:
        qdrant.upsert(collection_name=COLLECTION, points=points)
        print(f"Ingested {len(points)} chunks from {len(files)} files under {DATA_DIR}")
    else:
        print(f"No ingestible files found in {DATA_DIR}")


if __name__ == "__main__":
    main()
