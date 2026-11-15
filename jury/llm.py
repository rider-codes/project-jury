"""One wrapper for all model calls: provider swap, tiers, concurrency, backoff, budget."""

import asyncio
import json
import os
import random
from dataclasses import dataclass, field

import httpx

from jury.models import Tier

PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "GEMINI_API_KEY",
    ),
}


class BudgetExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


class Overloaded(LLMError):
    """A model is rate-limited upstream or erroring; another model may still work."""


@dataclass
class Budget:
    """Per-review cap on calls and tokens."""

    max_calls: int = 60
    max_tokens: int = 1_200_000
    calls: int = 0
    tokens: int = 0

    def reserve(self) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"call cap reached ({self.max_calls})")
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"token cap reached ({self.max_tokens})")
        self.calls += 1

    def record(self, tokens: int) -> None:
        self.tokens += tokens

    def can_afford(self, calls: int, margin: float = 1.25) -> bool:
        """Would `calls` more calls of the average size so far still fit?"""
        if self.calls + calls > self.max_calls:
            return False
        avg = self.tokens / self.calls if self.calls else 0
        return self.tokens + calls * avg * margin <= self.max_tokens


@dataclass
class LLM:
    provider: str
    api_key: str
    models: dict[Tier, str]
    budget: Budget = field(default_factory=Budget)
    max_concurrency: int = 2
    max_retries: int = 4
    timeout: float = 120.0
    _sem: asyncio.Semaphore | None = None
    last_model: str | None = None

    @classmethod
    def from_env(cls) -> "LLM":
        provider = os.environ.get("JURY_PROVIDER", "openrouter")
        if provider not in PROVIDERS:
            raise LLMError(f"unknown provider: {provider}")
        key = os.environ.get(PROVIDERS[provider][1], "")
        if not key:
            raise LLMError(f"{PROVIDERS[provider][1]} is not set (see .env.example)")
        models = {t: os.environ.get(f"JURY_MODEL_{t.value.upper()}", "") for t in Tier}
        return cls(
            provider=provider,
            api_key=key,
            models=models,
            budget=Budget(
                max_calls=int(os.environ.get("JURY_MAX_CALLS", 60)),
                max_tokens=int(os.environ.get("JURY_MAX_TOKENS", 1_200_000)),
            ),
            max_concurrency=int(os.environ.get("JURY_MAX_CONCURRENCY", 2)),
        )

    def models_for(self, tier: Tier) -> list[str]:
        """A tier may list several models, comma separated: the first is used, the rest are fallbacks."""
        raw = self.models.get(tier) or self.models.get(Tier.cheap) or ""
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if not models:
            raise LLMError(f"no model set for tier '{tier.value}' (JURY_MODEL_{tier.value.upper()})")
        return models

    def vision_models(self) -> list[str]:
        """Models that read screenshots: JURY_MODEL_VISION, else the mid tier."""
        raw = os.environ.get("JURY_MODEL_VISION", "")
        models = [m.strip() for m in raw.split(",") if m.strip()]
        return models or self.models_for(Tier.mid)

    def model_for(self, tier: Tier) -> str:
        return self.models_for(tier)[0]

    async def quota(self) -> dict | None:
        """Today's free-model requests on OpenRouter (this lookup is not itself a request).
        None when the provider has no such quota or the lookup fails."""
        if self.provider != "openrouter":
            return None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get("https://openrouter.ai/api/v1/key",
                                        headers={"Authorization": f"Bearer {self.api_key}"})
            data = resp.json().get("data", {})
        except (httpx.HTTPError, ValueError):
            return None
        daily = data.get("free_model_daily_requests") or {}
        all_free = all(m.endswith(":free") for t in Tier for m in self.models_for(t)) and all(
            m.endswith(":free") for m in self.vision_models())
        if not daily or not all_free:
            return None
        return {"remaining": daily.get("remaining"), "limit": daily.get("limit"), "used": daily.get("used")}

    async def complete_json(self, tier: Tier, messages: list[dict], vision: bool = False) -> dict:
        """Call the model and return its JSON object reply. Falls back to the tier's next model
        when one is overloaded upstream or erroring. vision: the messages hold images, so use
        the vision models instead of the tier's."""
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_concurrency)
        self.budget.reserve()
        url, _ = PROVIDERS[self.provider]
        models = self.vision_models() if vision else self.models_for(tier)
        data = None
        for i, model in enumerate(models):
            payload = {
                "model": model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.4,
            }
            has_fallback = i < len(models) - 1
            try:
                async with self._sem:
                    data = await self._post_with_retry(url, payload, fail_fast=has_fallback)
                self.last_model = model
                break
            except Overloaded:
                if not has_fallback:
                    raise
        assert data is not None
        self.budget.record(int((data.get("usage") or {}).get("total_tokens", 0)))
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected response shape: {str(data)[:300]}") from e
        if not content:  # reasoning models can spend the whole reply on thinking
            reason = data["choices"][0].get("finish_reason")
            raise LLMError(f"{payload['model']} returned no content (finish_reason={reason})")
        return parse_json_reply(content)

    async def _post_with_retry(self, url: str, payload: dict, fail_fast: bool = False) -> dict:
        """fail_fast: there is another model to try, so do not keep retrying an overloaded one."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    if _is_daily_cap(resp):
                        break  # the quota covers every free model, so falling back cannot help
                    if fail_fast and (_is_upstream_limit(resp) or attempt >= 1):
                        raise Overloaded(f"{payload['model']} (HTTP {resp.status_code}): {_reason(resp)}")
                    if attempt == self.max_retries:
                        break
                    retry_after = resp.headers.get("retry-after")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                    await asyncio.sleep(delay + random.random())
                    continue
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                return resp.json()
        if _is_daily_cap(resp):
            raise LLMError(f"daily free-model quota used up: {_reason(resp)}")
        raise Overloaded(f"gave up on {payload['model']} (HTTP {resp.status_code}): {_reason(resp)}")


def _is_upstream_limit(resp: httpx.Response) -> bool:
    return "rate-limited upstream" in resp.text or "upstream_provider" in resp.text


def _reason(resp: httpx.Response) -> str:
    """The provider's own explanation, e.g. 'temporarily rate-limited upstream'."""
    try:
        err = resp.json().get("error", {})
        return str((err.get("metadata") or {}).get("raw") or err.get("message") or resp.text)[:300]
    except ValueError:
        return resp.text[:300]


def _is_daily_cap(resp: httpx.Response) -> bool:
    """Retrying a per-day quota within seconds cannot help."""
    return "per-day" in resp.text or "free-models-per-day" in resp.text


def parse_json_reply(content: str) -> dict:
    """Models sometimes wrap JSON in code fences; strip them and parse."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"reply is not JSON: {content[:200]}")
    return json.loads(text[start : end + 1])
