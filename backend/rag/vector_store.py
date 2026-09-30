import faiss
import numpy as np
import os
import pickle

from backend.models.embedding_model import EmbeddingModel
from backend.utils.config import Config
from backend.utils.logger import logger


class VectorStore:
    def __init__(self):
        self.embedding_model = EmbeddingModel()
        self.index     = None
        self.documents = []
        self.dimension = 384   # default for all-MiniLM-L6-v2

    def reset(self):
        """Clear the in-memory index so each research run starts fresh."""
        self.index     = None
        self.documents = []
        logger.info("VectorStore reset — index cleared.")

    def add_documents(self, chunks):
        if not chunks:
            logger.warning("No chunks provided to add_documents.")
            return

        logger.info(f"Adding {len(chunks)} chunks to vector store.")
        texts = [chunk.page_content for chunk in chunks]
        embeddings = self.embedding_model.get_embeddings(texts)
        embeddings = np.array(embeddings, dtype="float32")

        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)

        if self.index is None:
            self.dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatL2(self.dimension)

        self.index.add(embeddings)
        self.documents.extend(chunks)
        logger.info(f"VectorStore now holds {len(self.documents)} chunks.")

    def search(self, query: str, k: int = 5) -> list:
        if self.index is None or not self.documents:
            logger.warning("Index is empty — cannot search.")
            return []

        k = min(k, len(self.documents))
        query_embedding = self.embedding_model.get_embeddings([query])
        query_embedding = np.array(query_embedding, dtype="float32")
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)

        distances, indices = self.index.search(query_embedding, k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx >= len(self.documents):
                continue
            results.append({
                "content":  self.documents[idx].page_content,
                "metadata": self.documents[idx].metadata,
                "score":    float(dist),
            })
        return results

    def save(self, path=None):
        path = path or Config.VECTOR_DB_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if self.index is not None:
            faiss.write_index(self.index, f"{path}.index")
            with open(f"{path}.docs", "wb") as f:
                pickle.dump(self.documents, f)
            logger.info(f"VectorStore saved to {path}.")

    def load(self, path=None):
        path = path or Config.VECTOR_DB_PATH
        if os.path.exists(f"{path}.index"):
            self.index = faiss.read_index(f"{path}.index")
            with open(f"{path}.docs", "rb") as f:
                self.documents = pickle.load(f)
            logger.info(f"VectorStore loaded from {path}.")
            return True
        return False
