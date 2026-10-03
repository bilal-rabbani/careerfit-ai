import json
import time
from dataclasses import dataclass, field
from typing import List, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from llm.config import NODE_SLOTS, DEFAULT_MODELS, REQUEST_TIMEOUT, MAX_RATE_LIMIT_WAIT

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


def _raise_for_status(r, cfg: KeyConfig):
    if r.status_code < 400:
        return
    msg = _error_message(r, cfg)
    if r.status_code == 429:
        try:
            ra = float(r.headers.get("retry-after"))
        except (TypeError, ValueError):
            ra = None
        raise RateLimitError(msg, ra)
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


def call_llm(node: str, keys: List[KeyConfig], system: str, user: str, schema: Type[T]) -> T:
    if not keys:
        raise QuotaExhausted("No API keys provided.")
    candidates = keys_for_node(node, keys)
    problems = {}

    for round_no in range(2):
        rate_limited = []
        for cfg in candidates:
            if cfg in problems and not isinstance(problems[cfg], RateLimitError):
                continue                              # auth/model errors won't fix themselves
            try:
                return _structured(cfg, system, user, schema)
            except RateLimitError as e:
                problems[cfg] = e
                rate_limited.append(e)
            except (AuthError, BadRequestError, BadOutputError, ProviderError) as e:
                problems[cfg] = e
        if round_no == 0 and rate_limited:
            waits = [MAX_RATE_LIMIT_WAIT if e.retry_after is None else e.retry_after
                     for e in rate_limited]
            time.sleep(min(max(waits), MAX_RATE_LIMIT_WAIT))
        else:
            break

    summary = "; ".join(f"{c.label}: {type(e).__name__}" for c, e in problems.items())
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
