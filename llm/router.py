import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import List, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from llm.config import (NODE_SLOTS, DEFAULT_MODELS, REQUEST_TIMEOUT, MAX_TOTAL_WAIT,
                        DEFAULT_COOLDOWN, MAX_COOLDOWN, MAX_RATE_LIMIT_TRIES)

T = TypeVar("T", bound=BaseModel)


# ---------- Errors (messages are always key-free) ----------
class LLMError(Exception): pass

class RateLimitError(LLMError):
    def __init__(self, msg="rate limited", retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after

class AuthError(LLMError): pass          # bad/revoked key
class BadRequestError(LLMError): pass    # wrong model name, unsupported option
class ProviderError(LLMError): pass      # 5xx, network, empty response (retryable)
class BadOutputError(LLMError): pass     # model never returned valid JSON
class QuotaExhausted(LLMError): pass     # nothing left to try


# ---------- Key config ----------
@dataclass(frozen=True)
class KeyConfig:
    provider: str
    key: str = field(repr=False)         # repr=False: never shows up in prints/logs
    model: str = ""

    def __post_init__(self):
        p = self.provider.lower().strip()
        if p not in DEFAULT_MODELS:
            raise ValueError(f"Unknown provider '{self.provider}'. Use: {list(DEFAULT_MODELS)}")
        object.__setattr__(self, "provider", p)
        object.__setattr__(self, "key", self.key.strip())
        if not self.model:
            object.__setattr__(self, "model", DEFAULT_MODELS[p])

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model} (...{self.key[-4:]})"


# ---------- HTTP layer ----------
def _error_message(r, cfg: KeyConfig) -> str:
    try:
        j = r.json()
        if isinstance(j, list) and j:
            j = j[0]
        err = j.get("error", j) if isinstance(j, dict) else j
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
    except ValueError:
        msg = r.text
    msg = str(msg).replace(cfg.key, "***")
    return f"HTTP {r.status_code}: {msg[:200]}"


def _parse_retry(r):
    """Seconds the provider asks us to wait (header or error text). None if unknown."""
    try:
        return float(r.headers.get("retry-after"))
    except (TypeError, ValueError):
        pass
    txt = r.text or ""
    m = re.search(r'retryDelay"?\s*:\s*"?(\d+(?:\.\d+)?)s', txt)
    if m:
        return float(m.group(1))
    m = re.search(r"try again in (?:(\d+)m)?\s*(\d+(?:\.\d+)?)s", txt)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    return None


def _raise_for_status(r, cfg: KeyConfig):
    if r.status_code < 400:
        return
    msg = _error_message(r, cfg)
    if r.status_code == 429:
        raise RateLimitError(msg, _parse_retry(r))
    if r.status_code in (401, 403) or (r.status_code == 400 and "api key" in msg.lower()):
        raise AuthError(msg)
    if r.status_code >= 500:
        raise ProviderError(msg)
    raise BadRequestError(msg)


def _raw_call(cfg: KeyConfig, system: str, user: str) -> str:
    """One HTTP request to the provider. Returns raw text."""
    try:
        if cfg.provider == "groq":
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {cfg.key}"},
                json={
                    "model": cfg.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=REQUEST_TIMEOUT,
            )
        else:  # gemini
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent",
                headers={"x-goog-api-key": cfg.key},   # header, not URL
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
                },
                timeout=REQUEST_TIMEOUT,
            )
    except (requests.Timeout, requests.ConnectionError) as e:
        raise ProviderError(f"network error: {type(e).__name__}")

    _raise_for_status(r, cfg)
    data = r.json()
    try:
        if cfg.provider == "groq":
            return data["choices"][0]["message"]["content"]
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        raise ProviderError("empty or blocked response")


@retry(
    retry=retry_if_exception_type(ProviderError),   # only transient errors
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _call_with_retry(cfg, system, user):
    return _raw_call(cfg, system, user)


# ---------- Structured output ----------
def _extract_json(text: str) -> str:
    """Strip ```json fences and surrounding chatter."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return text[start:end + 1]


def _structured(cfg: KeyConfig, system: str, user: str, schema: Type[T]) -> T:
    full_system = (
        system
        + "\n\nReturn ONLY a valid JSON object matching this JSON Schema. "
          "No markdown, no commentary.\n"
        + json.dumps(schema.model_json_schema())
    )
    last_err = ""
    for attempt in range(2):                         # 1 normal try + 1 repair try
        prompt = user if attempt == 0 else (
            user + f"\n\nYour previous reply was invalid ({last_err}). "
                   "Return corrected JSON only."
        )
        text = _call_with_retry(cfg, full_system, prompt)
        try:
            return schema.model_validate_json(_extract_json(text))
        except (ValidationError, ValueError) as e:
            last_err = str(e).replace("\n", " ")[:400]
    raise BadOutputError(f"invalid JSON from {cfg.label}: {last_err}")


# ---------- Public API ----------
def keys_for_node(node: str, keys: List[KeyConfig]) -> List[KeyConfig]:
    """Preferred key first (slot wraps around), then the others, duplicates removed."""
    start = NODE_SLOTS[node]
    ordered = [keys[(start + i) % len(keys)] for i in range(len(keys))]
    return list(dict.fromkeys(ordered))


_STATE_LOCK = threading.Lock()
_KEY_LOCKS = {}
_COOLDOWN = {}      # key config -> time.time() when it may be used again


def _key_lock(cfg):
    with _STATE_LOCK:
        return _KEY_LOCKS.setdefault(cfg, threading.Lock())


def call_llm(node: str, keys: List[KeyConfig], system: str, user: str, schema: Type[T]) -> T:
    """Calls on the same key run one at a time. A rate-limited key cools down for every caller."""
    if not keys:
        raise QuotaExhausted("No API keys provided.")
    alive = keys_for_node(node, keys)
    problems, tries = {}, {}
    start = time.time()
    while alive and time.time() - start < MAX_TOTAL_WAIT:
        alive.sort(key=lambda c: _COOLDOWN.get(c, 0.0))         # stable: slot preference kept when none are cooling
        cfg = alive[0]
        try:
            with _key_lock(cfg):
                wait = _COOLDOWN.get(cfg, 0.0) - time.time()
                if wait > 0:
                    time.sleep(min(wait, MAX_COOLDOWN))
                return _structured(cfg, system, user, schema)
        except RateLimitError as e:
            hint = e.retry_after if e.retry_after is not None else DEFAULT_COOLDOWN
            delay = min(hint + 1, MAX_COOLDOWN) if hint > 0 else 0
            _COOLDOWN[cfg] = time.time() + delay
            problems[cfg] = e
            tries[cfg] = tries.get(cfg, 0) + 1
            if tries[cfg] >= MAX_RATE_LIMIT_TRIES:
                alive.remove(cfg)
        except (AuthError, BadRequestError, BadOutputError, ProviderError) as e:
            problems[cfg] = e
            alive.remove(cfg)
    summary = "; ".join(f"{c.label}: {type(e).__name__}" for c, e in problems.items()) or "timed out waiting for rate limits"
    raise QuotaExhausted(f"All keys failed for '{node}'. {summary}")


# ---------- Test keys button ----------
class Ping(BaseModel):
    ok: bool = True


def test_keys(keys: List[KeyConfig]) -> List[dict]:
    """Send a tiny request per unique key. Returns [{label, status, detail}]."""
    results = []
    for cfg in dict.fromkeys(keys):
        try:
            _structured(cfg, "You are a health check. Set ok to true.", "ping", Ping)
            results.append({"label": cfg.label, "status": "ok", "detail": ""})
        except RateLimitError:
            results.append({"label": cfg.label, "status": "rate_limited",
                            "detail": "Key works but is rate limited right now."})
        except AuthError:
            results.append({"label": cfg.label, "status": "invalid",
                            "detail": "Key rejected. Check for typos or the wrong provider."})
        except BadRequestError as e:
            results.append({"label": cfg.label, "status": "bad_model", "detail": str(e)[:150]})
        except LLMError as e:
            results.append({"label": cfg.label, "status": "error", "detail": str(e)[:150]})
    return results
