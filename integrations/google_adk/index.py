import os
import urllib.request
from pathlib import Path

import pypdfium2 as pdfium
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models
from tqdm import tqdm

PDF_URL = "https://data.imf.org/-/media/iData/External-Storage/Documents/7FC05452C6C743D2BFB6188D2E248A38/en/2025-FAS-Annual-Report.pdf"
PDF_PATH = Path("annual_report.pdf")
DB_PATH = Path("db")
COLLECTION_NAME = "fas"
MODEL_NAME = "jinaai/jina-embeddings-v2-small-en"

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
# No Opik credentials -> skip the (heavy, networked) download + embedding so CI stays fast.
DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)


def download_pdf() -> None:
    if PDF_PATH.exists():
        return
    urllib.request.urlretrieve(PDF_URL, PDF_PATH)

def load_pdf_chunks(pdf_path: str, chunk_size: int = 500) -> list[str]:
    pdf = pdfium.PdfDocument(pdf_path)
    text = " ".join(page.get_textpage().get_text_range() for page in pdf)
    words = text.split()
    return [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]

def index_documents(chunks: list[str], batch_size: int = 16) -> None:
    embed_model = TextEmbedding(model_name=MODEL_NAME)
    client = QdrantClient(path=str(DB_PATH))

    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=512, distance=models.Distance.COSINE),
    )

    point_id = 0
    for i in tqdm(range(0, len(chunks), batch_size)):
        batch_chunks = chunks[i : i + batch_size]
        vectors = [list(vec) for vec in embed_model.embed(batch_chunks)]
        points = [
            models.PointStruct(
                id=point_id + j,
                vector=vec,
                payload={"doc_id": f"doc_{point_id + j}", "text": chunk},
            )
            for j, (vec, chunk) in enumerate(zip(vectors, batch_chunks))
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        point_id += len(batch_chunks)


def main() -> None:
    if DRY_RUN:
        print("[DRY RUN] Opik credentials not set — skipping PDF download + indexing.")
        return
    download_pdf()
    chunks = load_pdf_chunks(str(PDF_PATH))
    index_documents(chunks)
    print("indexing done")


if __name__ == "__main__":
    main()