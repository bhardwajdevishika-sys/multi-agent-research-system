import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev_key")
    
    # API Keys
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
    
    # -------------------------------------------------------------------------
    # HuggingFace Inference API — Top 3 models (remote, no local download)
    # -------------------------------------------------------------------------
    # 1. Mixtral-8x7B-Instruct-v0.1  — MoE powerhouse, best quality
    # 2. Meta-Llama-3-8B-Instruct     — Strong Meta instruction model
    # 3. Gemma-2-9B-IT                — Google's top open model
    # -------------------------------------------------------------------------
    LLM_MODEL_ID       = os.getenv("LLM_MODEL_ID",       "mistralai/Mixtral-8x7B-Instruct-v0.1")
    LLM_MODEL_FALLBACK_1 = os.getenv("LLM_MODEL_FALLBACK_1", "meta-llama/Meta-Llama-3-8B-Instruct")
    LLM_MODEL_FALLBACK_2 = os.getenv("LLM_MODEL_FALLBACK_2", "google/gemma-2-9b-it")

    # Ordered fallback chain used by LLMLoader
    LLM_MODEL_CHAIN = [
        os.getenv("LLM_MODEL_ID",         "mistralai/Mixtral-8x7B-Instruct-v0.1"),
        os.getenv("LLM_MODEL_FALLBACK_1", "meta-llama/Meta-Llama-3-8B-Instruct"),
        os.getenv("LLM_MODEL_FALLBACK_2", "google/gemma-2-9b-it"),
    ]

    # Embedding model — small local model (~90 MB), used via sentence-transformers
    # Also tried via HF Inference API first (see EmbeddingModel)
    EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2")
    DEVICE = os.getenv("DEVICE", "cpu")
    
    # RAG
    CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE",    1000))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
    VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "backend/memory/research_memory/faiss_index")
    
    # Search
    MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", 5))
    
    # Paths — BASE_DIR is the project root (one level above backend/)
    BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    MEMORY_DIR = os.path.join(BASE_DIR, "backend", "memory", "research_memory")
    CACHE_DIR  = os.path.join(BASE_DIR, "backend", "memory", "cache")
    UPLOAD_DIR = os.path.join(BASE_DIR, "backend", "memory", "uploads")

# Ensure required directories exist on import
for _directory in [Config.MEMORY_DIR, Config.CACHE_DIR, Config.UPLOAD_DIR]:
    os.makedirs(_directory, exist_ok=True)
