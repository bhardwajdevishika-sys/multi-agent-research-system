"""
Centralized logger factory for the Multi-Research Agent system.

Usage in any module:
    from backend.utils.logger import get_logger
    logger = get_logger(__name__)

A single default `logger` instance is also exported for backwards
compatibility with existing imports.
"""

import logging
import os
from datetime import datetime


def get_logger(name: str = "research_agent") -> logging.Logger:
    """
    Return a named logger that writes to both stdout and a daily log file.
    Calling this multiple times with the same name is safe — handlers are
    added only once.
    """
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "backend", "logs")
    log_dir = os.path.normpath(log_dir)
    os.makedirs(log_dir, exist_ok=True)

    log = logging.getLogger(name)
    if log.handlers:          # already configured — don't double-add
        return log

    log.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    # Daily rotating file handler
    log_file = os.path.join(log_dir, f"research_{datetime.now().strftime('%Y%m%d')}.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)

    log.addHandler(ch)
    log.addHandler(fh)
    return log


# ── Backwards-compatible default instance ────────────────────────────────────
logger = get_logger("research_agent")
