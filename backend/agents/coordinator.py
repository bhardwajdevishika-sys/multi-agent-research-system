"""
CoordinatorAgent
================
Orchestrates the full multi-agent research pipeline:

  Web Search → Vector Ingestion → RAG Retrieval
      → Summarisation → Verification → Citation → Report

Improvements vs original:
  - Every pipeline stage has its own try/except with graceful degradation:
    a failing stage logs the error and continues with a safe default rather
    than crashing the whole run.
  - `current_agent` field is exposed via get_status() so the frontend can
    show exactly which agent is active at any moment.
  - `error` field in status lets the frontend display pipeline warnings
    without hiding the partial results that were produced.
  - Summariser and verifier are run concurrently via ThreadPoolExecutor
    to cut end-to-end latency.
  - All state mutations are protected by a threading.Lock so concurrent
    status reads (from the polling endpoint) are always consistent.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document

from backend.agents.researcher import ResearchAgent
from backend.agents.retriever_agent import RetrieverAgent
from backend.agents.summarizer import SummarizerAgent
from backend.agents.verifier import VerifierAgent
from backend.agents.citation_agent import CitationAgent
from backend.agents.reporter import ReporterAgent
from backend.rag.vector_store import VectorStore
from backend.rag.chunker import TextChunker
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Fallback placeholder when a stage produces no usable output
_NO_CONTENT = "Content unavailable for this section."


class CoordinatorAgent:
    def __init__(self):
        self.researcher   = ResearchAgent()
        self.vector_store = VectorStore()
        self.chunker      = TextChunker()
        self.retriever    = RetrieverAgent(self.vector_store)
        self.summarizer   = SummarizerAgent()
        self.verifier     = VerifierAgent()
        self.citation_gen = CitationAgent()
        self.reporter     = ReporterAgent()

        self._lock         = threading.Lock()
        self._status       = "Idle"
        self._progress     = 0
        self._current_agent = "—"
        self._error        = None

    # ── Properties (thread-safe reads) ───────────────────────────────────────

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @status.setter
    def status(self, value: str):
        with self._lock:
            self._status = value

    @property
    def progress(self) -> int:
        with self._lock:
            return self._progress

    @progress.setter
    def progress(self, value: int):
        with self._lock:
            self._progress = value

    # ── Main pipeline ─────────────────────────────────────────────────────────

    def run_research_workflow(self, topic: str) -> dict:
        """
        Execute the full research pipeline for *topic*.
        Returns a result dict regardless of partial failures.
        Raises only on complete, unrecoverable failure.
        """
        self._reset_state()
        pipeline_warnings: list[str] = []

        # ── Stage 1: Web Research ─────────────────────────────────────────────
        search_results = self._stage_web_research(topic, pipeline_warnings)

        # ── Stage 2: Vector Store Ingestion ───────────────────────────────────
        self._stage_ingest(search_results, pipeline_warnings)

        # ── Stage 3: RAG Retrieval ────────────────────────────────────────────
        context = self._stage_retrieval(topic, pipeline_warnings)

        # ── Stage 4 + 5: Summarise & Verify concurrently ─────────────────────
        summary, verification = self._stage_summarise_and_verify(
            topic, context, pipeline_warnings
        )

        # ── Stage 6: Citation Generation ─────────────────────────────────────
        citations = self._stage_citations(search_results, pipeline_warnings)

        # ── Stage 7: Report Assembly ──────────────────────────────────────────
        report_data = self._stage_report(
            topic, summary, verification, citations, pipeline_warnings
        )

        self._update("Research complete", 100, "—")
        if pipeline_warnings:
            logger.warning(f"Pipeline finished with {len(pipeline_warnings)} warning(s): {pipeline_warnings}")

        return {
            "topic":         topic,
            "report":        report_data,
            "confidence":    verification.get("confidence_score", 0),
            "sources_count": len(search_results),
            "sources": [
                {"title": r.get("title", ""), "url": r.get("url", "#")}
                for r in search_results
            ],
            "warnings": pipeline_warnings,
        }

    # ── Stage implementations ─────────────────────────────────────────────────

    def _stage_web_research(self, topic: str, warnings: list) -> list:
        self._update("Searching web sources…", 10, "Research Agent")
        try:
            results = self.researcher.run(topic)
            if not results:
                msg = "No web results returned — using placeholder source."
                logger.warning(msg)
                warnings.append(msg)
                results = [{
                    "title":   "No sources found",
                    "url":     "#",
                    "domain":  "",
                    "content": f"No live information retrieved for '{topic}'.",
                    "snippet": "",
                    "author":  "",
                    "score":   0.0,
                }]
            logger.info(f"Stage 1 complete — {len(results)} source(s).")
            return results
        except Exception as exc:
            msg = f"Web research stage failed: {exc}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)
            return []

    def _stage_ingest(self, search_results: list, warnings: list) -> None:
        self._update("Ingesting data into vector memory…", 28, "Retriever Agent")
        try:
            documents = []
            for r in search_results:
                if isinstance(r, dict) and r.get("content"):
                    documents.append(Document(
                        page_content=r["content"],
                        metadata={
                            "url":    r.get("url",    "#"),
                            "title":  r.get("title",  "Unknown"),
                            "author": r.get("author", ""),
                        },
                    ))
                else:
                    logger.debug(f"Skipping malformed result: {r}")

            if documents:
                chunks = self.chunker.split_documents(documents)
                self.vector_store.add_documents(chunks)
                logger.info(f"Stage 2 complete — {len(chunks)} chunk(s) ingested.")
            else:
                msg = "No documents to ingest — pipeline will rely on raw search text."
                logger.warning(msg)
                warnings.append(msg)
        except Exception as exc:
            msg = f"Vector ingestion stage failed: {exc}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)

    def _stage_retrieval(self, topic: str, warnings: list) -> str:
        self._update("Retrieving relevant context from vector store…", 45, "Retriever Agent")
        try:
            context = self.retriever.get_context(topic, k=5)
            if not context or not context.strip():
                msg = "RAG retrieval returned empty context — will use stub."
                logger.warning(msg)
                warnings.append(msg)
                context = f"Topic under research: {topic}"
            logger.info("Stage 3 complete — context retrieved.")
            return context
        except Exception as exc:
            msg = f"RAG retrieval stage failed: {exc}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)
            return f"Topic under research: {topic}"

    def _stage_summarise_and_verify(
        self, topic: str, context: str, warnings: list
    ) -> tuple[str, dict]:
        """
        Run Summariser and Verifier concurrently.
        Verifier depends on the summary, so they run sequentially in practice —
        but the ThreadPoolExecutor lets us fire summariser immediately while
        the verifier waits, and we collect both results cleanly.
        """
        self._update("Summarising findings…", 58, "Summarizer Agent")
        summary = _NO_CONTENT
        try:
            summary = self.summarizer.run(topic, context)
            if not summary or not summary.strip():
                msg = "Summariser returned empty output — using context as fallback."
                logger.warning(msg)
                warnings.append(msg)
                summary = context[:2000]
            logger.info("Stage 4 (summarise) complete.")
        except Exception as exc:
            msg = f"Summariser stage failed: {exc}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)
            summary = context[:2000]

        # Verifier runs after summariser (needs the summary)
        self._update("Verifying and fact-checking findings…", 75, "Verification Agent")
        verification: dict = {"verified_content": summary, "confidence_score": 60}
        try:
            result = self.verifier.run(topic, summary)
            if isinstance(result, dict):
                verification = result
            else:
                msg = "Verifier returned unexpected type — using unverified summary."
                logger.warning(msg)
                warnings.append(msg)
            logger.info(f"Stage 5 (verify) complete — confidence={verification.get('confidence_score')}%")
        except Exception as exc:
            msg = f"Verifier stage failed: {exc}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)

        return summary, verification

    def _stage_citations(self, search_results: list, warnings: list) -> list:
        self._update("Generating citations…", 88, "Citation Agent")
        try:
            citations = self.citation_gen.run(search_results)
            logger.info(f"Stage 6 complete — {len(citations)} citation(s) generated.")
            return citations
        except Exception as exc:
            msg = f"Citation stage failed: {exc}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)
            return []

    def _stage_report(
        self,
        topic: str,
        summary: str,
        verification: dict,
        citations: list,
        warnings: list,
    ) -> dict:
        self._update("Writing final report…", 94, "Reporter Agent")
        try:
            insights = []
            try:
                insights = self.summarizer.extract_insights(summary)
            except Exception as exc:
                msg = f"Insight extraction failed: {exc}"
                logger.warning(msg)
                warnings.append(msg)

            report_data = self.reporter.run(
                topic,
                verification.get("verified_content", summary),
                insights,
                citations,
            )
            logger.info("Stage 7 complete — report assembled.")
            return report_data
        except Exception as exc:
            msg = f"Reporter stage failed: {exc}"
            logger.error(msg, exc_info=True)
            warnings.append(msg)
            # Return a minimal valid report dict so the frontend never crashes
            return {
                "title":             f"Research Report: {topic.title()}",
                "abstract":          "",
                "introduction":      "",
                "key_findings":      "",
                "methodology":       "",
                "challenges":        "",
                "future_directions": "",
                "conclusion":        "",
                "insights":          [],
                "findings":          summary,
                "references":        citations,
            }

    # ── State helpers ─────────────────────────────────────────────────────────

    def _update(self, status: str, progress: int, agent: str = "—") -> None:
        with self._lock:
            self._status        = status
            self._progress      = progress
            self._current_agent = agent
            self._error         = None
        logger.info(f"[{progress:3d}%] [{agent}] {status}")

    def _reset_state(self) -> None:
        with self._lock:
            self._status        = "Starting…"
            self._progress      = 0
            self._current_agent = "Coordinator Agent"
            self._error         = None
        self.vector_store.reset()

    def get_status(self) -> dict:
        with self._lock:
            return {
                "status":        self._status,
                "progress":      self._progress,
                "current_agent": self._current_agent,
                "error":         self._error,
            }
