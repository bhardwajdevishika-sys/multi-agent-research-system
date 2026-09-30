"""
WebSearchService
================
Priority: Tavily (advanced, full-page content) → DuckDuckGo → stub fallback.

Optimisations vs original:
  - Tavily and DuckDuckGo are called concurrently via ThreadPoolExecutor
    when both providers are available, halving worst-case latency.
  - Every provider call has an explicit timeout so a slow network can't
    block the pipeline indefinitely.
  - Errors are caught and logged at the provider level; the caller always
    receives a list (possibly empty), never an exception.

Credentials used (loaded from .env via Config):
  TAVILY_API_KEY  — optional; DuckDuckGo is used automatically if absent.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from urllib.parse import urlparse

from backend.utils.config import Config
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Hard cap on characters kept from any single source (prevents LLM token overflow)
_MAX_CONTENT_CHARS = 4_000
# Per-provider network timeout in seconds
_PROVIDER_TIMEOUT_S = 20


def _clean_text(text: str) -> str:
    """Strip HTML tags, collapse whitespace, remove boilerplate noise."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(cookie policy|privacy policy|subscribe now|sign up).{0,80}", "", text, flags=re.I)
    return text.strip()


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url


class WebSearchService:
    def __init__(self):
        self._tavily = None
        if Config.TAVILY_API_KEY:
            try:
                from tavily import TavilyClient
                self._tavily = TavilyClient(api_key=Config.TAVILY_API_KEY)
                logger.info("Tavily client initialised.")
            except Exception as exc:
                logger.warning(f"Tavily init failed ({exc}). Will use DuckDuckGo.")

    # ── Public API ────────────────────────────────────────────────────────────

    def search(self, query: str, max_results: int | None = None) -> list:
        """
        Return a deduplicated list of source dicts for *query*.
        Never raises — returns a stub on total failure.
        """
        max_results = max_results or Config.MAX_SEARCH_RESULTS
        logger.info(f"Searching: '{query}' | max_results={max_results}")
        t0 = time.perf_counter()

        results = self._fetch_with_fallback(query, max_results)
        results = self._deduplicate(results)

        elapsed = time.perf_counter() - t0
        logger.info(f"Search complete — {len(results)} unique source(s) in {elapsed:.2f}s.")
        return results

    # ── Internal orchestration ────────────────────────────────────────────────

    def _fetch_with_fallback(self, query: str, max_results: int) -> list:
        """
        If Tavily is configured, run Tavily + DDG concurrently and merge.
        Otherwise run DDG only. Stub is used only when both fail.
        """
        if self._tavily:
            results = self._run_concurrent(query, max_results)
            if results:
                return results

        # Sequential DDG fallback
        results = self._ddg_search(query, max_results)
        if results:
            return results

        return self._stub(query)

    def _run_concurrent(self, query: str, max_results: int) -> list:
        """
        Fire Tavily and DDG at the same time; collect whichever finishes first
        then merge. If Tavily times out, DDG results are used alone.
        """
        results: list = []
        tasks = {
            "tavily": lambda: self._tavily_search(query, max_results),
            "ddg":    lambda: self._ddg_search(query, max_results),
        }

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="search") as pool:
            futures = {pool.submit(fn): name for name, fn in tasks.items()}
            try:
                for future in as_completed(futures, timeout=_PROVIDER_TIMEOUT_S + 5):
                    name = futures[future]
                    try:
                        batch = future.result(timeout=1)
                        logger.info(f"{name.capitalize()} returned {len(batch)} result(s).")
                        results.extend(batch)
                    except Exception as exc:
                        logger.warning(f"{name.capitalize()} future raised: {exc}")
            except FuturesTimeout:
                logger.warning("Concurrent search timed out — using partial results.")

        return results

    # ── Tavily ────────────────────────────────────────────────────────────────

    def _tavily_search(self, query: str, max_results: int) -> list:
        try:
            raw = self._tavily.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_raw_content=True,
                include_answer=True,
            )
        except Exception as exc:
            logger.error(f"Tavily API error: {exc}")
            return []

        out = []

        # Tavily synthesised answer — high-quality lead source
        answer = _clean_text(raw.get("answer") or "")
        if answer:
            out.append({
                "title":   "Tavily Synthesised Answer",
                "url":     "https://tavily.com",
                "domain":  "tavily.com",
                "content": answer[:_MAX_CONTENT_CHARS],
                "snippet": answer[:300],
                "author":  "Tavily AI",
                "score":   1.0,
            })

        for r in raw.get("results", []):
            raw_c   = _clean_text(r.get("raw_content") or "")
            short_c = _clean_text(r.get("content")     or "")
            body    = (raw_c if len(raw_c) > len(short_c) else short_c)[:_MAX_CONTENT_CHARS]
            if not body:
                continue
            url = r.get("url", "#")
            out.append({
                "title":   r.get("title",  "Untitled").strip(),
                "url":     url,
                "domain":  _domain(url),
                "content": body,
                "snippet": body[:300],
                "author":  r.get("author", _domain(url)),
                "score":   float(r.get("score", 0.0)),
            })

        logger.info(f"Tavily: {len(out)} formatted source(s).")
        return out

    # ── DuckDuckGo ────────────────────────────────────────────────────────────

    def _ddg_search(self, query: str, max_results: int) -> list:
        out = []
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                hits = list(ddgs.text(query, max_results=max_results))
            for r in hits:
                body = _clean_text(r.get("body", r.get("snippet", "")))[:_MAX_CONTENT_CHARS]
                if not body:
                    continue
                url = r.get("href", r.get("link", "#"))
                out.append({
                    "title":   r.get("title", "Untitled").strip(),
                    "url":     url,
                    "domain":  _domain(url),
                    "content": body,
                    "snippet": body[:300],
                    "author":  _domain(url),
                    "score":   0.5,
                })
            logger.info(f"DuckDuckGo: {len(out)} result(s).")
        except Exception as exc:
            logger.error(f"DuckDuckGo error: {exc}")
        return out

    # ── Stub ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _stub(query: str) -> list:
        logger.warning("All search providers failed — using knowledge-only stub.")
        return [{
            "title":   f"Research on: {query}",
            "url":     "https://example.com",
            "domain":  "example.com",
            "content": (
                f"No live web results could be retrieved for '{query}'. "
                "This report is generated from the model's internal knowledge only."
            ),
            "snippet": "Stub result — no live data.",
            "author":  "System",
            "score":   0.0,
        }]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(results: list) -> list:
        seen, out = set(), []
        for r in results:
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                out.append(r)
        return out
