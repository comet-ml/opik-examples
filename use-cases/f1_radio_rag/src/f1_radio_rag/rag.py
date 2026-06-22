import threading

import chromadb
import litellm
import opik

from . import config
from .prompts import SYSTEM_PROMPT, user_prompt

_collection = None
_collection_lock = threading.Lock()


def get_collection():
    # WHY: cache one PersistentClient. evaluate()/run_tests() call the task across worker
    # threads, and concurrent PersistentClient creation races on tenant validation.
    global _collection
    if _collection is None:
        with _collection_lock:
            if _collection is None:
                client = chromadb.PersistentClient(path=config.CHROMA_DIR)
                _collection = client.get_or_create_collection(
                    name=config.COLLECTION, metadata={"hnsw:space": "cosine"}
                )
    return _collection


def ingest(messages: list[dict]) -> int:
    collection = get_collection()
    collection.upsert(
        ids=[m["id"] for m in messages],
        documents=[m["text"] for m in messages],
        metadatas=[
            {"session": m["session"], "driver": m["driver"], "team": m["team"], "lap": m["lap"]}
            for m in messages
        ],
    )
    return collection.count()


def retrieve(query: str, k: int = 5) -> list[str]:
    collection = get_collection()
    result = collection.query(query_texts=[query], n_results=k)
    return result["documents"][0] if result["documents"] else []


def _generate(query: str, context_text: str) -> str:
    response = litellm.completion(
        model=config.GEN_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(query, context_text)},
        ],
    )
    return response.choices[0].message.content


@opik.track(project_name=config.OPIK_PROJECT_NAME)
def answer(query: str, k: int = 5) -> dict:
    context = retrieve(query, k)
    output = _generate(query, "\n".join(context))
    return {"input": query, "output": output, "context": context}
