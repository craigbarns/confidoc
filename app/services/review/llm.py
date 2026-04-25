"""ConfiDoc Backend — Review Agent LLM Helpers with Circuit Breaker & Cache."""

import hashlib
import json
import time
from typing import Any, Dict

import httpx

from app.config import get_settings
from app.core.json_utils import extract_json as parse_json
from app.core.logging import get_logger

logger = get_logger(__name__)

class ReviewAgentTransientError(RuntimeError):
    """Provider-side issue that should not expose raw HTTP details to users."""
    def __init__(
        self,
        message: str,
        *,
        code: str = "llm_unavailable",
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


# ── Simple In-Memory Cache (L1) ───────────────────────────────────────
# In production, this should be backed by Redis (L2).
_llm_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 3600 * 24 * 7  # 7 days


def _get_cache_key(prompt: str, system: str, model: str) -> str:
    payload = f"{system}:{model}:{prompt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Simple Circuit Breaker ───────────────────────────────────────────
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.error("circuit_breaker_opened", failures=self.failures)

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def can_proceed(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF-OPEN"
                return True
            return False
        return True  # HALF-OPEN


_mistral_breaker = CircuitBreaker()


async def llm_call(prompt: str, *, system: str = "", temperature: float = 0.1) -> str:
    settings = get_settings()
    
    # 1. Check Cache
    cache_key = _get_cache_key(prompt, system, settings.MISTRAL_MODEL)
    cached = _llm_cache.get(cache_key)
    if cached and (time.time() - cached["timestamp"] < _CACHE_TTL):
        logger.info("llm_cache_hit", key=cache_key)
        return cached["content"]

    # 2. Try Mistral with Circuit Breaker
    if _mistral_breaker.can_proceed() and settings.MISTRAL_ENABLED:
        try:
            content = await _call_mistral(prompt, system, temperature)
            _mistral_breaker.record_success()
            
            # Save to cache
            _llm_cache[cache_key] = {"content": content, "timestamp": time.time()}
            return content
        except ReviewAgentTransientError as exc:
            _mistral_breaker.record_failure()
            logger.warning("mistral_failed_checking_fallback", error=str(exc))
            # Fall through to fallback
        except Exception as exc:
            _mistral_breaker.record_failure()
            logger.error("mistral_unexpected_error", error=str(exc))
            # Fall through

    # 3. Fallback to Ollama if enabled
    if settings.OLLAMA_ENABLED:
        try:
            logger.info("llm_fallback_to_ollama")
            return await _call_ollama(prompt, system)
        except Exception as exc:
            logger.error("ollama_fallback_failed", error=str(exc))

    raise ReviewAgentTransientError(
        "Tous les moteurs d'analyse sont indisponibles. Réessayez plus tard.",
        code="all_llms_unavailable"
    )


async def _call_mistral(prompt: str, system: str, temperature: float) -> str:
    settings = get_settings()
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY manquant")

    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": settings.MISTRAL_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    timeout = float(settings.MISTRAL_TIMEOUT_SECONDS)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.MISTRAL_BASE_URL.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise ReviewAgentTransientError("Mistral timeout", code="llm_timeout") from exc
    except httpx.RequestError as exc:
        raise ReviewAgentTransientError("Mistral network error", code="llm_network_error") from exc

    _raise_for_llm_status(resp)
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    return str(choices[0].get("message", {}).get("content") or "")


async def _call_ollama(prompt: str, system: str) -> str:
    settings = get_settings()
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    body = {
        "model": settings.OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }
    timeout = float(settings.OLLAMA_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=body)
    resp.raise_for_status()
    data = resp.json()
    return str(data.get("response", ""))


def _retry_after_seconds(resp: httpx.Response) -> int | None:
    value = resp.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0, int(float(value)))
    except ValueError:
        return None


def _raise_for_llm_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return

    retry_after = _retry_after_seconds(resp)
    if resp.status_code == 429:
        raise ReviewAgentTransientError(
            "Mistral rate limit",
            code="mistral_rate_limited",
            retry_after_seconds=retry_after,
        )
    if resp.status_code in {401, 403}:
        raise ReviewAgentTransientError("Mistral auth error", code="mistral_auth_error")
    if resp.status_code >= 500:
        raise ReviewAgentTransientError("Mistral provider error", code="llm_provider_error")

    resp.raise_for_status()
