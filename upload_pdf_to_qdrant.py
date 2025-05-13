import uuid
import pdfplumber
import re
import chardet
from pathlib import Path
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models

# --- Config ---
PDF_FILE = "C:\\Users\\steve\\Documents\\Project Folder\\New folder\\A1882-04.pdf"
COLLECTION_NAME = "legal_chunks"
CHUNK_SIZE = 300  # words
OVERLAP = 50  # word overlap between chunks

# --- Initialize Qdrant (local embedded) ---
client = QdrantClient(path="qdrant_local_db")
embedder = SentenceTransformer("sentence-transformers/multi-qa-distilbert-cos-v1")

# --- Prepare Collection if Not Exists ---
embedding_dim = embedder.get_sentence_embedding_dimension()
if not client.collection_exists(COLLECTION_NAME):
    client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE)
    )

# --- Read PDF and Clean Text ---
def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def clean_text(text: str) -> str:
    # Detect encoding issues and normalize
    if isinstance(text, bytes):
        encoding = chardet.detect(text)["encoding"] or "utf-8"
        text = text.decode(encoding, errors="ignore")
    text = text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")

    # Remove non-printable characters
    text = re.sub(r'[^\x20-\x7E\n]+', '', text)

    # Normalize weird quotes and characters
    replacements = {
        'â€™': "'", 'â€œ': '"', 'â€': '"', 'â€“': '-', 'â€”': '-', 'â€¦': '...',
        'Ã©': 'é', 'Ã¨': 'è', 'Â': ''
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    return text.strip()

# --- Chunk Text ---
def chunk_text(text: str, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks

# --- Embed and Store Chunks in Qdrant ---
def store_chunks(chunks):
    points = []
    for chunk in chunks:
        vector = embedder.encode(chunk).tolist()
        points.append(models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"text": chunk}
        ))
    client.upsert(collection_name=COLLECTION_NAME, points=points)

# --- Main Execution ---
if __name__ == "__main__":
    raw_text = extract_text_from_pdf(PDF_FILE)
    cleaned_text = clean_text(raw_text)
    text_chunks = chunk_text(cleaned_text)
    store_chunks(text_chunks)
    print(f"Stored {len(text_chunks)} chunks in Qdrant from '{PDF_FILE}'")
