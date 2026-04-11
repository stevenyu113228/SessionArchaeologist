"""RAG vector store — ChromaDB backed with OpenAI embeddings."""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb

from archaeologist.config import settings

logger = logging.getLogger(__name__)

_client: chromadb.ClientAPI | None = None
PERSIST_DIR = Path("data/vectordb")


def get_chroma() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    return _client


def get_collection(session_id: str) -> chromadb.Collection:
    """Get or create a collection for a session."""
    client = get_chroma()
    name = f"session_{session_id.replace('-', '_')[:48]}"
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def embed_turns(session_id: str, turns: list) -> int:
    """Embed all turns for a session into ChromaDB.

    Args:
        session_id: Session UUID string.
        turns: List of Turn ORM objects or dicts.

    Returns:
        Number of documents embedded.
    """
    from archaeologist.llm.client import embed

    collection = get_collection(session_id)

    # Batch turns for embedding
    batch_size = 50
    total = 0

    for i in range(0, len(turns), batch_size):
        batch = turns[i:i + batch_size]

        ids = []
        documents = []
        metadatas = []

        for turn in batch:
            turn_idx = turn.turn_index if hasattr(turn, 'turn_index') else turn['turn_index']
            text = turn.content_text if hasattr(turn, 'content_text') else turn['content_text']
            role = turn.role if hasattr(turn, 'role') else turn['role']
            is_error = turn.is_error if hasattr(turn, 'is_error') else turn.get('is_error', False)

            if not text or len(text.strip()) < 10:
                continue

            # For long turns, split into chunks
            segments = _split_text(text, max_chars=6000)
            for seg_idx, segment in enumerate(segments):
                doc_id = f"turn_{turn_idx}_seg_{seg_idx}"
                ids.append(doc_id)
                documents.append(segment)
                metadatas.append({
                    "turn_index": turn_idx,
                    "role": role,
                    "is_error": is_error,
                    "segment": seg_idx,
                    "has_tool_call": bool(
                        (turn.tool_calls if hasattr(turn, 'tool_calls') else turn.get('tool_calls'))
                    ),
                })

        if not documents:
            continue

        # Get embeddings
        embeddings = embed(documents, model=settings.embedding_model)

        # Upsert into ChromaDB
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        total += len(documents)
        logger.info("Embedded batch %d-%d (%d docs)", i, i + len(batch), len(documents))

    logger.info("Total embedded: %d documents for session %s", total, session_id)
    return total


def search(
    session_id: str,
    query: str,
    mode: str = "semantic",
    n_results: int = 10,
    filters: dict | None = None,
) -> list[dict]:
    """Search the session's vector store.

    Args:
        session_id: Session UUID string.
        query: Search query text.
        mode: "semantic", "keyword", or "hybrid".
        n_results: Number of results.
        filters: Optional metadata filters (role, is_error, turn_index range).

    Returns:
        List of result dicts with content_text, turn_index, role, score.
    """
    from archaeologist.llm.client import embed

    collection = get_collection(session_id)

    if collection.count() == 0:
        return []

    # Build where clause from filters
    where = None
    if filters:
        conditions = []
        if "role" in filters:
            conditions.append({"role": filters["role"]})
        if "is_error" in filters:
            conditions.append({"is_error": filters["is_error"]})
        if "min_turn" in filters:
            conditions.append({"turn_index": {"$gte": filters["min_turn"]}})
        if "max_turn" in filters:
            conditions.append({"turn_index": {"$lte": filters["max_turn"]}})
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

    if mode == "keyword":
        # Use ChromaDB's document search (contains)
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    else:
        # Semantic search using embedding
        query_embedding = embed([query], model=settings.embedding_model)[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    # Format results
    output = []
    if results and results["documents"]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "content_text": doc,
                "turn_index": meta.get("turn_index"),
                "role": meta.get("role"),
                "is_error": meta.get("is_error", False),
                "score": 1.0 - dist if dist else 0.0,  # cosine distance → similarity
            })

    return output


def _split_text(text: str, max_chars: int = 6000) -> list[str]:
    """Split text into segments, preferring paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    segments = []
    paragraphs = text.split('\n\n')
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            segments.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        segments.append(current.strip())

    return segments if segments else [text[:max_chars]]
