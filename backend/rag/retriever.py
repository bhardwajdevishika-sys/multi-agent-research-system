from backend.rag.vector_store import VectorStore
from backend.utils.logger import logger


class RAGRetriever:
    def __init__(self, vector_store=None):
        self.vector_store = vector_store or VectorStore()

    def retrieve(self, query: str, k: int = 5) -> list:
        logger.info(f"Retrieving top-{k} chunks for query: {query}")
        return self.vector_store.search(query, k=k)

    def get_context_string(self, query: str, k: int = 5) -> str:
        """
        Returns a rich context block that includes source metadata so the
        LLM knows where each piece of information came from.
        """
        results = self.retrieve(query, k=k)
        if not results:
            return "No relevant context found in the knowledge base."

        parts = []
        for i, r in enumerate(results, 1):
            meta    = r.get("metadata", {})
            title   = meta.get("title", "Unknown Source")
            url     = meta.get("url",   "#")
            content = r.get("content",  "").strip()
            parts.append(
                f"[Source {i}] {title}\n"
                f"URL: {url}\n"
                f"{content}"
            )

        return "\n\n---\n\n".join(parts)
