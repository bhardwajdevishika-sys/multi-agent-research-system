"""
ResearchAgent
=============
Orchestrates web search and returns a clean, deduplicated list of source dicts.

Improvements vs original:
  - Per-source content validation (skips empty/malformed entries).
  - Configurable max_results forwarded from coordinator.
  - Structured error logging with exc_info for full tracebacks.
  - Returns an empty list on failure instead of propagating exceptions,
    letting the coordinator decide how to handle missing data gracefully.
"""

from backend.services.web_search import WebSearchService
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ResearchAgent:
    def __init__(self):
        self.search_service = WebSearchService()

    def run(self, topic: str, max_results: int | None = None) -> list:
        """
        Search the web for *topic* and return a list of cleaned source dicts.
        Each dict is guaranteed to have: title, url, domain, content, snippet, author, score.
        Never raises — returns [] on error so the coordinator can degrade gracefully.
        """
        logger.info(f"ResearchAgent: starting search for '{topic}'")
        try:
            raw_results = self.search_service.search(topic, max_results=max_results)
        except Exception as exc:
            logger.error(f"ResearchAgent: search service raised unexpectedly: {exc}", exc_info=True)
            return []

        if not raw_results:
            logger.warning("ResearchAgent: no results returned by search service.")
            return []

        # Validate and normalise each result
        valid = []
        for i, res in enumerate(raw_results):
            if not isinstance(res, dict):
                logger.warning(f"ResearchAgent: skipping non-dict result at index {i}.")
                continue
            content = (res.get("content") or "").strip()
            if not content:
                logger.warning(f"ResearchAgent: skipping result with empty content — '{res.get('title', 'N/A')}'")
                continue
            valid.append({
                "title":   (res.get("title")  or "Untitled").strip(),
                "url":     (res.get("url")    or "#").strip(),
                "domain":  (res.get("domain") or "").strip(),
                "content": content,
                "snippet": (res.get("snippet") or content[:300]).strip(),
                "author":  (res.get("author")  or "").strip(),
                "score":   float(res.get("score", 0.0)),
            })

        logger.info(f"ResearchAgent: {len(valid)} valid source(s) ready (of {len(raw_results)} fetched).")
        return valid
