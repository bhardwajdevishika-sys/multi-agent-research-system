"""
LLMLoader — HuggingFace Serverless Inference API client.

Model priority (Config.LLM_MODEL_CHAIN):
  1. mistralai/Mixtral-8x7B-Instruct-v0.1   — best quality
  2. meta-llama/Meta-Llama-3-8B-Instruct    — strong instruction model
  3. google/gemma-2-9b-it                   — reliable fallback

All inference is remote — no local model download.
"""

from huggingface_hub import InferenceClient
from backend.utils.config import Config
from backend.utils.logger import logger


class LLMLoader:
    """Singleton wrapper around HuggingFace InferenceClient."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = None
            cls._instance._active_model = None
        return cls._instance

    def _get_client(self) -> InferenceClient:
        if self._client is None:
            token = Config.HUGGINGFACE_TOKEN
            if not token or not token.strip():
                raise ValueError(
                    "HUGGINGFACE_TOKEN is not set. Add it to .env and restart."
                )
            self._client = InferenceClient(token=token)
            logger.info("HuggingFace InferenceClient initialised (remote API).")
        return self._client

    def _call_model(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int,
    ) -> str:
        """Single chat-completion request with system + user roles."""
        client = self._get_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        logger.info(f"HF API → {model_id} (max_tokens={max_new_tokens})")
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=max_new_tokens,
            temperature=0.3,   # lower = more factual, less hallucination
            top_p=0.9,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""

    def load_model(self, model_id=None):
        """Compatibility shim — validates token eagerly."""
        self._active_model = model_id or Config.LLM_MODEL_CHAIN[0]
        self._get_client()
        logger.info(f"LLMLoader ready. Primary: {Config.LLM_MODEL_CHAIN[0]}")
        return self

    def query(
        self,
        user_prompt: str,
        system_prompt: str = "You are a professional research assistant. Be factual, precise, and structured.",
        max_length: int = 700,
    ) -> str:
        """
        Query the HF Inference API with system + user roles.
        Falls back through Config.LLM_MODEL_CHAIN on any failure.
        """
        last_error = None
        for model_id in Config.LLM_MODEL_CHAIN:
            try:
                result = self._call_model(
                    model_id, system_prompt, user_prompt, max_new_tokens=max_length
                )
                self._active_model = model_id
                logger.info(f"Response received from {model_id}")
                return result
            except Exception as exc:
                logger.warning(f"Model '{model_id}' failed: {exc}. Trying next…")
                last_error = exc

        logger.error(f"All models failed. Last error: {last_error}")
        return (
            "Unable to generate a response. "
            "All HuggingFace Inference API models are currently unavailable."
        )

    @property
    def active_model(self) -> str | None:
        return self._active_model
