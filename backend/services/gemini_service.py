"""
Google Gemini service – secondary AI provider / fallback.
Uses the official google-genai SDK (v3+).
"""
import time
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-genai not installed; Gemini unavailable")


class GeminiService:
    """Wrapper around Google Gemini API (google-genai SDK)."""

    def __init__(self, api_key: str, model_id: str):
        self.api_key = api_key
        self.model_id = model_id
        self._client = None
        self._available = False
        self._init()

    def _init(self):
        if not GEMINI_AVAILABLE:
            logger.error("google-genai package not available")
            return
        if not self.api_key:
            logger.warning("Gemini API key not configured; Gemini unavailable")
            return
        try:
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=genai_types.HttpOptions(timeout=30000),  # 30s timeout
            )
            self._available = True
            logger.info(f"Google Gemini initialized: {self.model_id}")
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        if not self._available:
            return {
                "success": False,
                "text": "",
                "model": self.model_id,
                "provider": "gemini",
                "duration_ms": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "error": "Gemini not available – check API key",
            }

        t0 = time.time()
        try:
            gen_config = genai_types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
            response = self._client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=gen_config,
            )
            duration_ms = round((time.time() - t0) * 1000, 1)
            # response.text can be None for some models; fall back to candidates
            text = response.text
            if text is None:
                try:
                    parts = response.candidates[0].content.parts
                    text = "".join(
                        p.text for p in parts if hasattr(p, "text") and p.text
                    )
                except (IndexError, AttributeError, TypeError):
                    text = ""
            usage = getattr(response, "usage_metadata", None)
            stripped = (text or "").strip()
            if not stripped:
                logger.warning("Gemini returned empty content")
                return {
                    "success": False,
                    "text": "",
                    "model": self.model_id,
                    "provider": "gemini",
                    "duration_ms": duration_ms,
                    "prompt_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                    "completion_tokens": 0,
                    "error": "Gemini returned empty response content",
                }
            logger.debug(f"Gemini OK in {duration_ms}ms")
            return {
                "success": True,
                "text": stripped,
                "model": self.model_id,
                "provider": "gemini",
                "duration_ms": duration_ms,
                "prompt_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                "completion_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                "error": None,
            }
        except Exception as e:
            duration_ms = round((time.time() - t0) * 1000, 1)
            logger.error(f"Gemini generate error: {e}")
            return {
                "success": False,
                "text": "",
                "model": self.model_id,
                "provider": "gemini",
                "duration_ms": duration_ms,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "error": str(e),
            }

    def test_connection(self) -> Dict[str, Any]:
        # Use a conversational prompt; pure-instruction prompts can yield empty responses
        result = self.generate(
            "Say the words 'Google Gemini operational' and nothing else.",
            max_tokens=20,
            temperature=0.1,
        )
        result["test"] = True
        # API connected successfully even if text is empty (model-dependent blank response)
        if result["success"] and not result.get("text"):
            result["note"] = "API connected; model returned empty content on test prompt"
        return result
