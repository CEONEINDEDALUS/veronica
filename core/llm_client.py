"""
Talks to a local Ollama server (native /api/tags, /api/show, /api/chat,
/api/embeddings). Also responsible for discovering each model's context
window so the rest of the app can budget prompts correctly instead of
silently truncating.
"""
from __future__ import annotations
import json
from typing import Generator, List, Dict, Optional
from urllib.parse import urlparse

import requests

DEFAULT_CONTEXT_WINDOW = 4096


def normalize_host(host: str) -> str:
    """Validate a user-supplied Ollama host and normalize it to a base URL.

    Accepts values like ``localhost:11434`` or ``http://localhost:11434`` and
    returns a scheme-qualified URL with the trailing slash stripped. Raises
    ``ValueError`` on clearly invalid input and returns an empty string when
    no host was provided.
    """
    host = (host or "").strip()
    if not host:
        return ""

    if "://" not in host:
        host = "http://" + host

    parsed = urlparse(host)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid Ollama host: {host!r}")

    return host.rstrip("/")


class LLMError(Exception):
    pass


class BaseLLMClient:
    def list_models(self) -> List[str]:
        raise NotImplementedError

    def get_context_window(self, model: str) -> int:
        raise NotImplementedError

    def chat_stream(self, model: str, messages: List[Dict], temperature: float = 0.4
                     ) -> Generator[str, None, None]:
        raise NotImplementedError

    def embed(self, model: str, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OllamaClient(BaseLLMClient):
    def __init__(self, host: str):
        self.host = host.rstrip("/")

    def list_models(self) -> List[str]:
        r = requests.get(f"{self.host}/api/tags", timeout=10)
        r.raise_for_status()
        data = r.json()
        return sorted(m["name"] for m in data.get("models", []))

    def get_context_window(self, model: str) -> int:
        try:
            r = requests.post(f"{self.host}/api/show", json={"name": model}, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return DEFAULT_CONTEXT_WINDOW

        # Newer Ollama exposes model_info with keys like "<family>.context_length"
        model_info = data.get("model_info", {}) or {}
        for key, value in model_info.items():
            if key.endswith("context_length") and isinstance(value, (int, float)):
                return int(value)

        # Fall back to an explicitly configured num_ctx parameter, if present
        params_str = data.get("parameters", "") or ""
        for line in params_str.splitlines():
            line = line.strip()
            if line.startswith("num_ctx"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return int(parts[1])

        return DEFAULT_CONTEXT_WINDOW

    def chat_stream(self, model: str, messages: List[Dict], temperature: float = 0.4,
                     context_window: int = DEFAULT_CONTEXT_WINDOW) -> Generator[str, None, None]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_ctx": min(context_window, DEFAULT_CONTEXT_WINDOW * 8)},
        }
        try:
            with requests.post(f"{self.host}/api/chat", json=payload, stream=True, timeout=300) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    if obj.get("done"):
                        break
                    piece = obj.get("message", {}).get("content", "")
                    if piece:
                        yield piece
        except requests.RequestException as e:
            raise LLMError(f"Ollama chat request failed: {e}")

    def embed(self, model: str, texts: List[str]) -> List[List[float]]:
        vectors = []
        for t in texts:
            try:
                r = requests.post(f"{self.host}/api/embeddings",
                                   json={"model": model, "prompt": t}, timeout=60)
                r.raise_for_status()
                vectors.append(r.json()["embedding"])
            except requests.RequestException as e:
                raise LLMError(f"Ollama embeddings request failed: {e}")
        return vectors


def get_client(ollama_host: str) -> BaseLLMClient:
    return OllamaClient(ollama_host)
