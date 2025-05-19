from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from llama_cpp import Llama
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
import time

# Initialize LLaMA model
llm = Llama(
    model_path="C:\\Users\\steve\\Desktop\\legal-assistance\\backend\\unsloth.Q5_K_M.gguf",
    n_ctx=2048,
    n_threads=4,
    stream=True
)
  
client = QdrantClient(path="qdrant_local_db")  # Local embedded storage
COLLECTION_NAME = "legal_chunks"

embedder = SentenceTransformer("sentence-transformers/multi-qa-distilbert-cos-v1")
# -------------------- Create Collection (if not exists) --------------------
embedding_dim = embedder.get_sentence_embedding_dimension()

# client.recreate_collection(
#     collection_name=COLLECTION_NAME,
#     vectors_config=models.VectorParams(
#         size=embedding_dim,
#         distance=models.Distance.COSINE
#     )
# )
    
existing_collections = [col.name for col in client.get_collections().collections]

if COLLECTION_NAME not in existing_collections:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=embedding_dim,
            distance=models.Distance.COSINE
        )
    )
    print(f"Collection '{COLLECTION_NAME}' created.")
else:
    print(f"Collection '{COLLECTION_NAME}' already exists.")    

app = FastAPI()

# CORS settings
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str


# -------------------- RAG Logic --------------------
# def retrieve_context(query: str, top_k=3) -> str:
#     query_vector = embedder.encode(query).tolist()
#     results = client.search(
#         collection_name=COLLECTION_NAME,
#         query_vector=query_vector,
#         limit=top_k
#     )
#     context_chunks = [hit.payload["text"] for hit in results if "text" in hit.payload]
#     return "\n".join(context_chunks)

def retrieve_context(query: str, top_k=3) -> str:
    try:
        query_vector = embedder.encode(query).tolist()
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k
        )
        context_chunks = [hit.payload["text"] for hit in results if "text" in hit.payload]
        return "\n".join(context_chunks)
    except Exception as e:
        return f"[Error in context retrieval] {e}"


def stream_response(prompt: str):
    try:
        context = retrieve_context(prompt)
        full_prompt = f"[INST] You are a legal assistant specializing in Indian law. Answer the user's question strictly according to Indian legal principles, acts, and case laws. Do not reference or rely on laws from other countries.Use the following legal context to answer the question:\n{context}\nQuestion: {prompt} [/INST]"

        for output in llm(prompt=full_prompt, max_tokens=500, stop=["</s>"], stream=True):
            text = output.get("choices", [{}])[0].get("text", "")
            if text:
                yield text
                time.sleep(0.02)
    except Exception as e:
        yield f"\n[Error] {str(e)}\n"

@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(stream_response(request.message), media_type="text/plain")
