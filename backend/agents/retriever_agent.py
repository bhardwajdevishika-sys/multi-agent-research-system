from backend.rag.retriever import RAGRetriever
from backend.utils.logger import logger

class RetrieverAgent:
    def __init__(self, vector_store=None):
        self.retriever = RAGRetriever(vector_store)

    def run(self, query, k=5):
        logger.info(f"Retriever Agent fetching context for: {query}")
        results = self.retriever.retrieve(query, k=k)
        return results

    def get_context(self, query, k=5):
        return self.retriever.get_context_string(query, k=k)
