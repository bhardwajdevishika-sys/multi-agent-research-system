"""
EmbeddingModel — HuggingFace Serverless Inference API client for embeddings.

Primary path : HF Inference API (feature_extraction endpoint, remote, no download).
Fallback path: local sentence-transformers model (~90 MB, CPU-only).

The fallback is triggered automatically if the API call fails (e.g. token
quota exceeded, network issue, model temporarily unavailable).
"""

import numpy as np
from huggingface_hub import InferenceClient
from backend.utils.config import Config
from backend.utils.logger import logger


class EmbeddingModel:
    """Singleton wrapper for text embeddings."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingModel, cls).__new__(cls)
            cls._instance._client = None
            cls._instance._local_model = None
            cls._instance._use_local = False
        return cls._instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> InferenceClient:
        """Return a cached InferenceClient, creating it on first call."""
        if self._client is None:
            token = Config.HUGGINGFACE_TOKEN
            if not token or not token.strip():
                raise ValueError(
                    "HUGGINGFACE_TOKEN is not set. "
                    "Add it to your .env file and restart the app."
                )
            self._client = InferenceClient(token=token)
            logger.info("HuggingFace InferenceClient initialised for embeddings (remote API).")
        return self._client

    def _get_local_model(self):
        """Lazy-load the local sentence-transformers fallback model."""
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer
            model_id = Config.EMBEDDING_MODEL_ID
            logger.info(f"Loading local fallback embedding model: {model_id}")
            self._local_model = SentenceTransformer(model_id, device=Config.DEVICE)
            logger.info("Local embedding model loaded successfully.")
        return self._local_model

    @staticmethod
    def _normalise_api_response(result) -> list:
        """
        The HF feature_extraction endpoint can return several shapes:
          - 1-D list  : single sentence embedding  → use directly
          - 2-D list  : token-level embeddings      → mean-pool to 1-D
          - 3-D list  : batch of token embeddings   → mean-pool axis=1

        Always returns a plain Python list (1-D vector).
        """
        arr = np.array(result, dtype=np.float32)
        if arr.ndim == 1:
            return arr.tolist()
        elif arr.ndim == 2:
            return arr.mean(axis=0).tolist()
        elif arr.ndim == 3:
            # (batch=1, seq_len, hidden) — squeeze batch dim then mean-pool tokens
            return arr[0].mean(axis=0).tolist()
        else:
            raise ValueError(f"Unexpected embedding response shape: {arr.shape}")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_model(self, model_id=None):
        """
        Compatibility shim — validates the token eagerly so callers get an
        early error rather than failing silently at query time.
        """
        self._get_client()
        logger.info(
            f"EmbeddingModel ready (HF Inference API). "
            f"Model: {Config.EMBEDDING_MODEL_ID}"
        )
        return self

    def get_embeddings(self, texts) -> list:
        """
        Encode a list of strings into embedding vectors.

        Tries the HF Inference API first; falls back to the local
        sentence-transformers model if the API call fails.

        Args:
            texts: A single string or a list of strings.

        Returns:
            List of embedding vectors (each is a list of floats).
        """
        if isinstance(texts, str):
            texts = [texts]

        # ── Remote API path ──────────────────────────────────────────────────
        if not self._use_local:
            try:
                client = self._get_client()
                model_id = Config.EMBEDDING_MODEL_ID
                logger.info(
                    f"Getting embeddings via HF Inference API → {model_id} "
                    f"({len(texts)} text(s))"
                )

                embeddings = []
                for text in texts:
                    result = client.feature_extraction(text, model=model_id)
                    embedding = self._normalise_api_response(result)
                    embeddings.append(embedding)

                logger.info(f"Successfully got {len(embeddings)} embeddings from API.")
                return embeddings

            except Exception as exc:
                logger.warning(
                    f"HF Inference API embedding failed: {exc}. "
                    "Switching to local sentence-transformers fallback."
                )
                self._use_local = True

        # ── Local fallback path ──────────────────────────────────────────────
        local_model = self._get_local_model()
        embeddings = local_model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()
