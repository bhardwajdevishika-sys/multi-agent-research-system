from backend.utils.logger import logger

class Reranker:
    """Simple reranker to improve retrieval quality."""
    
    @staticmethod
    def rerank(query, documents):
        logger.info(f"Reranking {len(documents)} documents for query: {query}")
        # In a production system, we'd use a Cross-Encoder here.
        # For now, we'll keep the documents as is or perform simple keyword boost.
        # This is a placeholder for more advanced reranking logic.
        return sorted(documents, key=lambda x: x.get('score', 0))
