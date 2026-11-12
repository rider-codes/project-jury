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


@dataclass
class Budget:
    """Per-review cap on calls and tokens."""

    max_calls: int = 60
    max_tokens: int = 500_000
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
                max_tokens=int(os.environ.get("JURY_MAX_TOKENS", 500_000)),
            ),
            max_concurrency=int(os.environ.get("JURY_MAX_CONCURRENCY", 2)),
        )

    def model_for(self, tier: Tier) -> str:
        model = self.models.get(tier) or self.models.get(Tier.cheap)
        if not model:
            raise LLMError(f"no model set for tier '{tier.value}' (JURY_MODEL_{tier.value.upper()})")
        return model

    async def complete_json(self, tier: Tier, messages: list[dict]) -> dict:
        """Call the model and return its JSON object reply."""
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_concurrency)
        self.budget.reserve()
        url, _ = PROVIDERS[self.provider]
        payload = {
            "model": self.model_for(tier),
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
        }
        async with self._sem:
            data = await self._post_with_retry(url, payload)
        self.budget.record(int((data.get("usage") or {}).get("total_tokens", 0)))
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected response shape: {str(data)[:300]}") from e
        if not content:  # reasoning models can spend the whole reply on thinking
            reason = data["choices"][0].get("finish_reason")
            raise LLMError(f"{payload['model']} returned no content (finish_reason={reason})")
        return parse_json_reply(content)

    async def _post_with_retry(self, url: str, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == self.max_retries or _is_daily_cap(resp):
                        break
                    retry_after = resp.headers.get("retry-after")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                    await asyncio.sleep(delay + random.random())
                    continue
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                return resp.json()
        raise LLMError(f"gave up on {payload['model']} (HTTP {resp.status_code}): {_reason(resp)}")


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
