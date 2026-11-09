"""One LLM client for every role, over OpenAI-compatible chat endpoints.

Swapping a model = changing one line in .env (LLM1_MODEL / LLM2_MODEL / LLM3_MODEL /
TRANSLATE_MODEL, format "provider:model"). Adding a provider = one entry in PROVIDERS.

There is no silent fallback to fake output: if every configured model fails, LLMError
is raised and the pipeline shows an honest "service unavailable" message.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from config.settings import API_KEYS, FALLBACK_MODELS, ROLE_MODELS

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "bearer"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "bearer"),
    "sarvam": ("https://api.sarvam.ai/v1/chat/completions", "sarvam"),
    "openai": ("https://api.openai.com/v1/chat/completions", "bearer"),
}
JSON_MODE_PROVIDERS = {"groq", "gemini", "openai"}


class LLMError(RuntimeError):
    pass


@dataclass
class UsageLog:
    """Per-consultation record of every model call (shown in the UI and used for cost estimates)."""
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, **kw):
        self.calls.append(kw)

    def totals(self) -> Dict[str, int]:
        return {
            "calls": len(self.calls),
            "prompt_tokens": sum(c.get("prompt_tokens", 0) for c in self.calls),
            "completion_tokens": sum(c.get("completion_tokens", 0) for c in self.calls),
        }


def parse_json(text: str) -> Dict[str, Any]:
    """Extract the first JSON object from a model reply (tolerates ``` fences and chatter)."""
    t = re.sub(r"<think>[\s\S]*?</think>", "", text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(t[start:end + 1])


class LLMClient:
    def __init__(self, role: str, usage: Optional[UsageLog] = None, timeout: float = 60.0):
        self.role = role
        self.usage = usage if usage is not None else UsageLog()
        self.timeout = timeout
        primary = ROLE_MODELS[role]
        self.chain = [primary] + [m for m in FALLBACK_MODELS if m != primary]

    @property
    def model(self) -> str:
        return self.chain[0]

    def _call(self, spec: str, messages, json_mode: bool, max_tokens: int, temperature: float) -> str:
        provider, model = spec.split(":", 1)
        url, auth = PROVIDERS[provider]
        key = API_KEYS.get(provider, "")
        if not key:
            raise LLMError(f"no API key for {provider}")
        headers = {"Content-Type": "application/json"}
        headers.update({"api-subscription-key": key} if auth == "sarvam" else {"Authorization": f"Bearer {key}"})
        payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode and provider in JSON_MODE_PROVIDERS:
            payload["response_format"] = {"type": "json_object"}

        last_err = None
        for attempt in range(2):  # one quick retry on rate-limit / server error
            t0 = time.time()
            try:
                r = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
            except httpx.HTTPError as e:
                last_err = f"{provider} network error: {e}"
                continue
            if r.status_code == 200:
                data = r.json()
                content = (data["choices"][0]["message"].get("content") or "")
                content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                u = data.get("usage") or {}
                self.usage.add(role=self.role, model=spec, ms=int((time.time() - t0) * 1000),
                               prompt_tokens=u.get("prompt_tokens", 0),
                               completion_tokens=u.get("completion_tokens", 0))
                if content:
                    return content
                raise LLMError(f"{provider} returned empty content (token budget used up?)")  # next provider
            else:
                last_err = f"{provider} HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            time.sleep(1.5 * (attempt + 1))
        raise LLMError(last_err or "unknown error")

    def chat(self, system: str, user: str, json_mode: bool = False,
             max_tokens: int = 2048, temperature: float = 0.1) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        errors = []
        for spec in self.chain:
            try:
                return self._call(spec, messages, json_mode, max_tokens, temperature)
            except (LLMError, KeyError, ValueError) as e:
                errors.append(f"{spec}: {e}")
        raise LLMError(" | ".join(errors))

    def chat_json(self, system: str, user: str, max_tokens: int = 2048) -> Dict[str, Any]:
        raw = self.chat(system, user, json_mode=True, max_tokens=max_tokens)
        try:
            return parse_json(raw)
        except (ValueError, json.JSONDecodeError):
            raw = self.chat(system + "\n\nReturn ONLY one valid JSON object. No prose, no code fences.",
                            user, json_mode=True, max_tokens=max_tokens)
            return parse_json(raw)  # raises if still invalid; caller decides how to fail safely
