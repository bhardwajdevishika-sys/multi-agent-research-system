"""
Research API Routes
===================
All endpoints are under the /api prefix (registered in app.py).

Endpoints:
  POST /api/research       — start a research run (async, 202) or return cache hit (200)
  GET  /api/status         — poll coordinator progress + current agent
  GET  /api/result         — retrieve the latest completed result
  POST /api/settings       — update runtime settings (maxResults etc.)
  POST /api/upload-pdf     — upload a PDF for RAG ingestion
  GET  /api/report         — download final report as PDF or DOCX

Thread safety:
  - A threading.Lock guards all writes to `latest_research` and coordinator
    state resets so concurrent requests don't corrupt state.
"""

import os
import threading

from flask import Blueprint, request, jsonify, send_file

from backend.agents.coordinator import CoordinatorAgent
from backend.services.pdf_service import PDFService
from backend.services.report_service import ReportService
from backend.services.cache_service import CacheService
from backend.utils.config import Config
from backend.utils.logger import get_logger

logger = get_logger(__name__)

research_bp    = Blueprint("research", __name__)
coordinator    = CoordinatorAgent()
cache_service  = CacheService()

# Shared state protected by a lock
_state_lock      = threading.Lock()
_latest_research: dict = {}
_research_running = False


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _set_latest(data: dict) -> None:
    with _state_lock:
        _latest_research["data"] = data


def _get_latest() -> dict | None:
    with _state_lock:
        return _latest_research.get("data")


def _mark_running(flag: bool) -> None:
    global _research_running
    with _state_lock:
        _research_running = flag


# ─── POST /api/research ───────────────────────────────────────────────────────

@research_bp.route("/research", methods=["POST"])
def start_research():
    data      = request.get_json(silent=True) or {}
    topic     = data.get("topic", "").strip()
    use_cache = data.get("use_cache", True)

    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    # Block a second run while one is already in progress
    with _state_lock:
        if _research_running:
            return jsonify({
                "error": "A research run is already in progress. "
                         "Please wait for it to complete or reset the system."
            }), 409

    # Return cached result immediately if available
    if use_cache:
        cached = cache_service.get_cached_research(topic)
        if cached:
            _set_latest(cached)
            logger.info(f"Cache hit: '{topic}'")
            return jsonify({"message": "Research retrieved from cache", "data": cached}), 200

    # Reset coordinator and kick off background thread
    coordinator.status   = "Starting…"
    coordinator.progress = 0
    _mark_running(True)

    def _background(t: str) -> None:
        try:
            result = coordinator.run_research_workflow(t)
            _set_latest(result)
            cache_service.cache_research(t, result)
            logger.info(f"Research complete for '{t}'.")
        except Exception as exc:
            logger.error(f"Background research failed for '{t}': {exc}", exc_info=True)
            coordinator.status   = f"Error: {exc}"
            coordinator.progress = 0
        finally:
            _mark_running(False)

    thread = threading.Thread(target=_background, args=(topic,), daemon=True)
    thread.start()

    return jsonify({"message": "Research started", "topic": topic}), 202


# ─── GET /api/status ─────────────────────────────────────────────────────────

@research_bp.route("/status", methods=["GET"])
def get_status():
    """
    Returns coordinator progress, current status string, active agent name,
    and any non-fatal error message. Frontend polls this every few seconds.
    """
    status = coordinator.get_status()
    return jsonify(status), 200


# ─── GET /api/result ─────────────────────────────────────────────────────────

@research_bp.route("/result", methods=["GET"])
def get_result():
    result = _get_latest()
    if result is None:
        return jsonify({"error": "No research result available yet. Start a research run first."}), 404

    sources = result.get("sources", [])
    if not sources:
        # Fallback: reconstruct from citations
        for ref in result.get("report", {}).get("references", []):
            if isinstance(ref, str):
                sources.append({"title": ref, "url": "#"})
            elif isinstance(ref, dict):
                sources.append(ref)

    return jsonify({
        "topic":      result.get("topic",      ""),
        "report":     result.get("report",     {}),
        "confidence": result.get("confidence", 0),
        "sources":    sources,
        "warnings":   result.get("warnings",   []),
    }), 200


# ─── POST /api/settings ──────────────────────────────────────────────────────

@research_bp.route("/settings", methods=["POST"])
def update_settings():
    """
    Applies runtime settings from the frontend settings modal.
    Supports: maxResults (int).
    Model selection is handled by the LLMLoader fallback chain.
    """
    data = request.get_json(silent=True) or {}

    max_results = data.get("maxResults")
    if max_results is not None:
        try:
            Config.MAX_SEARCH_RESULTS = max(1, min(20, int(max_results)))
            logger.info(f"Settings updated: MAX_SEARCH_RESULTS={Config.MAX_SEARCH_RESULTS}")
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid maxResults value — must be an integer between 1 and 20."}), 400

    return jsonify({"message": "Settings updated successfully"}), 200


# ─── POST /api/upload-pdf ─────────────────────────────────────────────────────

@research_bp.route("/upload-pdf", methods=["POST"])
def upload_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    # Validate extension
    allowed = {".pdf"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"error": f"Only PDF uploads are supported (got '{ext}')."}), 415

    try:
        file_path = PDFService.save_uploaded_file(file)
        return jsonify({"message": "File uploaded successfully.", "path": file_path}), 200
    except Exception as exc:
        logger.error(f"PDF upload failed: {exc}", exc_info=True)
        return jsonify({"error": "File upload failed — see server logs for details."}), 500


# ─── GET /api/report ─────────────────────────────────────────────────────────

@research_bp.route("/report", methods=["GET"])
def get_report():
    format_type = request.args.get("format", "pdf").lower()
    if format_type not in ("pdf", "docx"):
        return jsonify({"error": "Unsupported format. Use ?format=pdf or ?format=docx"}), 400

    result = _get_latest()
    if result is None:
        return jsonify({"error": "No research data available. Run a research query first."}), 404

    report_data = result.get("report", {})
    topic       = result.get("topic", "report").replace(" ", "_")
    output_path = os.path.join(Config.MEMORY_DIR, f"{topic}_report.{format_type}")

    try:
        if format_type == "pdf":
            ok = ReportService.generate_pdf(report_data, output_path)
        else:
            ok = ReportService.generate_docx(report_data, output_path)

        if not ok or not os.path.exists(output_path):
            raise RuntimeError("Report file was not created.")

        return send_file(
            output_path,
            as_attachment=True,
            download_name=os.path.basename(output_path),
        )
    except Exception as exc:
        logger.error(f"Report generation failed ({format_type}): {exc}", exc_info=True)
        return jsonify({"error": "Failed to generate report. See server logs for details."}), 500
