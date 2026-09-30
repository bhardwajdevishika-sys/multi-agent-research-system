"""
EmbeddingModel — HuggingFace Serverless Inference API client for embeddings.

Memory optimisation for free-tier hosting (512 MB RAM):
  - Primary path  : HF Inference API (remote, zero local memory for the model)
  - Fallback path : local sentence-transformers (lazy-loaded ONLY if API fails
                    AND the ALLOW_LOCAL_EMBEDDING env var is set to "true")

On Render free tier, torch + sentence-transformers are NOT installed
(removed from requirements to save ~800 MB). The app runs purely on the
HF Inference API for both LLM and embeddings.
"""

import os
import numpy as np
from huggingface_hub import InferenceClient
from backend.utils.config import Config
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Set ALLOW_LOCAL_EMBEDDING=true in .env to enable local fallback (local dev only)
_ALLOW_LOCAL = os.environ.get("ALLOW_LOCAL_EMBEDDING", "false").lower() == "true"


class EmbeddingModel:
    """Singleton wrapper for text embeddings via HF Inference API."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client      = None
            cls._instance._local_model = None
            cls._instance._use_local   = False
        return cls._instance

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_client(self) -> InferenceClient:
        if self._client is None:
            token = Config.HUGGINGFACE_TOKEN
            if not token or not token.strip():
                raise ValueError(
                    "HUGGINGFACE_TOKEN is not set. Add it to .env and restart."
                )
            self._client = InferenceClient(token=token)
            logger.info("HuggingFace InferenceClient initialised for embeddings (remote API).")
        return self._client

    def _get_local_model(self):
        """
        Lazy-load local sentence-transformers model.
        Only attempted when ALLOW_LOCAL_EMBEDDING=true (local dev).
        """
        if not _ALLOW_LOCAL:
            raise RuntimeError(
                "Local embedding model is disabled on this deployment "
                "(ALLOW_LOCAL_EMBEDDING != true). "
                "Set HUGGINGFACE_TOKEN so the remote API can be used."
            )
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                model_id = Config.EMBEDDING_MODEL_ID
                logger.info(f"Loading local fallback embedding model: {model_id}")
                self._local_model = SentenceTransformer(model_id, device=Config.DEVICE)
                logger.info("Local embedding model loaded.")
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Install it locally with: pip install sentence-transformers"
                )
        return self._local_model

    @staticmethod
    def _normalise(result) -> list:
        """
        HF feature_extraction can return several shapes:
          1-D → single sentence embedding (use directly)
          2-D → token-level embeddings (mean-pool → 1-D)
          3-D → batch of token embeddings (mean-pool axis=1)
        Always returns a flat 1-D Python list.
        """
        arr = np.array(result, dtype=np.float32)
        if arr.ndim == 1:
            return arr.tolist()
        elif arr.ndim == 2:
            return arr.mean(axis=0).tolist()
        elif arr.ndim == 3:
            return arr[0].mean(axis=0).tolist()
        raise ValueError(f"Unexpected embedding response shape: {arr.shape}")

    # ── Public interface ──────────────────────────────────────────────────────

    def load_model(self, model_id=None):
        """Eagerly validate the HF token so callers get a clear early error."""
        self._get_client()
        logger.info(f"EmbeddingModel ready. Model: {Config.EMBEDDING_MODEL_ID}")
        return self

    def get_embeddings(self, texts) -> list:
        """
        Encode a list of strings into embedding vectors.
        Uses HF Inference API (remote). Falls back to local model only if
        ALLOW_LOCAL_EMBEDDING=true and the API call fails.
        """
        if isinstance(texts, str):
            texts = [texts]

        # ── Remote API (primary) ──────────────────────────────────────────────
        if not self._use_local:
            try:
                client   = self._get_client()
                model_id = Config.EMBEDDING_MODEL_ID
                logger.info(f"Embedding {len(texts)} text(s) via HF API → {model_id}")
                embeddings = [
                    self._normalise(client.feature_extraction(t, model=model_id))
                    for t in texts
                ]
                logger.info(f"Got {len(embeddings)} embedding(s) from API.")
                return embeddings
            except Exception as exc:
                logger.warning(f"HF API embedding failed: {exc}. Trying local fallback.")
                self._use_local = True

        # ── Local fallback (only if explicitly enabled) ───────────────────────
        local = self._get_local_model()
        embeddings = local.encode(texts, show_progress_bar=False)
        return embeddings.tolist()
