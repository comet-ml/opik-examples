import threading

import chromadb
import litellm
import opik

from . import config

_collection = None
_collection_lock = threading.Lock()


def get_collection():
    # WHY: cache one PersistentClient. Optimizer/evaluate call the task across worker
    # threads; concurrent PersistentClient creation races on tenant validation.
    global _collection
    if _collection is None:
        with _collection_lock:
            if _collection is None:
                client = chromadb.PersistentClient(path=config.CHROMA_DIR)
                _collection = client.get_or_create_collection(
                    name=config.COLLECTION, metadata={"hnsw:space": "cosine"}
                )
    return _collection


def ingest(docs: list[dict]) -> int:
    collection = get_collection()
    collection.upsert(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[{"title": d["title"]} for d in docs],
    )
    return collection.count()


def retrieve(query: str, n_results: int = 3) -> list[str]:
    collection = get_collection()
    result = collection.query(query_texts=[query], n_results=n_results)
    return result["documents"][0]


@opik.track
def answer(query: str, system_prompt: str, model: str | None = None) -> str:
    context = "\n\n".join(retrieve(query))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
    ]
    response = litellm.completion(model=model or config.GEN_MODEL, messages=messages)
    return response.choices[0].message.content


@opik.track
def should_retrieve(query: str, model: str | None = None) -> bool:
    """Part 3 agent gate: decide whether this query needs a docs lookup."""
    messages = [
        {
            "role": "system",
            "content": (
                "You decide whether a user question about the Ledgerline product needs a "
                "documentation lookup. Answer with exactly YES or NO."
            ),
        },
        {"role": "user", "content": query},
    ]
    response = litellm.completion(model=model or config.GEN_MODEL, messages=messages)
    return response.choices[0].message.content.strip().upper().startswith("YES")
