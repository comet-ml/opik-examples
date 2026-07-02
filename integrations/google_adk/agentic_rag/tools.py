from ddgs import DDGS
from fastembed import TextEmbedding
from qdrant_client import QdrantClient

from index import COLLECTION_NAME, DB_PATH, MODEL_NAME

embed_model = TextEmbedding(model_name=MODEL_NAME)
client = QdrantClient(path=str(DB_PATH))


def retrieve_docs(query: str):
    """
    Search similar documents from the knowledge base.
    Args:
        query: User query used to retrieve relevant documents.
    """
    query_vector = list(embed_model.embed([query]))[0]

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=4,
        with_payload=True,
    )
    return [
        {
            "score": point.score,
            "text": point.payload["text"],
        }
        for point in results.points
    ]


def web_search(query: str) -> str:
    """
    Simple DuckDuckGo web search.
    Args:
        query: User query used to retrieve browsing results
    """
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=5)

    return "\n\n".join(r.get("body", "") for r in results)
