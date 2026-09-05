from __future__ import annotations
import json
import os
import threading
import logging
from typing import Generator, List, Dict, Optional, Any
from urllib.parse import urlparse
import requests
from pydantic import BaseModel

DEFAULT_CONTEXT_WINDOW = 8192
_SESS = None
_GGUF_CACHE: dict = {}
_GGUF_LOCK = threading.RLock()
logger = logging.getLogger(__name__)

def _sess():
    global _SESS
    if _SESS is None:
        s = requests.Session()
        a = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=1)
        s.mount("http://", a)
        s.mount("https://", a)
        _SESS = s
    return _SESS

def normalize_host(h: str) -> str:
    h = (h or "").strip()
    if not h:
        return ""
    if "://" not in h:
        h = "http://" + h
    p = urlparse(h)
    if not p.scheme or not p.netloc:
        raise ValueError(f"bad host {h!r}")
    if p.scheme not in ("http", "https"):
        raise ValueError("only http/https")
    if p.hostname in ("0.0.0.0", ""):
        raise ValueError("invalid host")
    return h.rstrip("/")


class LLMError(Exception):
    pass


class BaseLLMClient:
    def list_models(self) -> List[str]:
        raise NotImplementedError

    def get_context_window(self, m: str) -> int:
        raise NotImplementedError

    def chat_stream(self, m: str, msgs: List[Dict], temperature: float = 0.4, context_window: int = DEFAULT_CONTEXT_WINDOW) -> Generator[str, None, None]:
        raise NotImplementedError

    def chat_json(self, m: str, msgs: List[Dict], schema: Dict[str, Any], temperature: float = 0.0) -> Optional[str]:
        raise NotImplementedError

    def embed(self, m: str, txts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OllamaClient(BaseLLMClient):
    def __init__(self, h: str):
        self.host = h.rstrip("/")

    def list_models(self) -> List[str]:
        r = _sess().get(f"{self.host}/api/tags", timeout=8)
        r.raise_for_status()
        return sorted(x["name"] for x in r.json().get("models", []))

    def get_context_window(self, m: str) -> int:
        try:
            r = _sess().post(f"{self.host}/api/show", json={"name": m}, timeout=8)
            r.raise_for_status()
            d = r.json()
        except:
            return DEFAULT_CONTEXT_WINDOW
        mi = d.get("model_info", {}) or {}
        for k, v in mi.items():
            if k.endswith("context_length") and isinstance(v, (int, float)):
                return int(v)
        ps = d.get("parameters", "") or ""
        for l in ps.splitlines():
            l = l.strip()
            if l.startswith("num_ctx"):
                p = l.split()
                if len(p) >= 2 and p[1].isdigit():
                    return int(p[1])
        return DEFAULT_CONTEXT_WINDOW

    def chat_stream(self, m: str, msgs: List[Dict], temperature: float = 0.4, context_window: int = DEFAULT_CONTEXT_WINDOW) -> Generator[str, None, None]:
        payload = {"model": m, "messages": msgs, "stream": True, "options": {"temperature": temperature, "num_ctx": min(context_window, 16384)}}
        try:
            with _sess().post(f"{self.host}/api/chat", json=payload, stream=True, timeout=180) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        o = json.loads(line.decode())
                    except:
                        continue
                    if o.get("done"):
                        break
                    piece = o.get("message", {}).get("content", "")
                    if piece:
                        yield piece
        except requests.RequestException as e:
            raise LLMError(f"chat fail {e}")

    def chat_json(self, m: str, msgs: List[Dict], schema: Dict[str, Any], temperature: float = 0.0) -> Optional[str]:
        payload = {"model": m, "messages": msgs, "stream": False, "format": schema, "options": {"temperature": temperature}}
        try:
            r = _sess().post(f"{self.host}/api/chat", json=payload, timeout=120)
            r.raise_for_status()
        except requests.RequestException as e:
            raise LLMError(f"json chat fail {e}")
        d = r.json()
        c = d.get("message", {}).get("content", "")
        return c if c else None

    def embed(self, m: str, txts: List[str]) -> List[List[float]]:
        out = []
        s = _sess()
        for t in txts:
            t = t[:8000]
            try:
                r = s.post(f"{self.host}/api/embeddings", json={"model": m, "prompt": t}, timeout=30)
                r.raise_for_status()
                out.append(r.json()["embedding"])
            except requests.RequestException as e:
                raise LLMError(f"embed fail {e}")
        return out


def _gguf_threads(nt: int) -> int:
    if nt and nt > 0:
        return nt
    try:
        import os as _os
        c = _os.cpu_count() or 4
        # For large ctx (262k) use more threads; cap at 8 to avoid oversubscription
        # low_end_mode will still be respected via config, but auto should be faster
        return max(1, min(8, max(4, c - 2)))
    except:
        return 4


def _validate_gguf_path(path: str) -> str:
    """Return realpath after validating GGUF header. Raises LLMError if invalid."""
    if not path or not isinstance(path, str):
        raise LLMError(f"gguf path empty")
    # reject null bytes and overly long
    if "\x00" in path or len(path) > 4096:
        raise LLMError("invalid gguf path")
    real = os.path.realpath(path)
    # block directory traversal via symlink? realpath already resolves, but we check existence
    if not os.path.isfile(real):
        raise LLMError(f"gguf not found {path}")
    if os.path.getsize(real) == 0:
        raise LLMError(f"gguf empty {path}")
    # quick magic check before full parse to give fast feedback
    try:
        with open(real, "rb") as f:
            mg = f.read(4)
            if mg != b"GGUF":
                raise LLMError(f"not a GGUF file (bad magic {mg!r}) {path}")
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"gguf read fail {e}")
    # full header validation (alignment, sizes, SSTI etc.)
    try:
        from core.gguf_validator import validate_gguf_file, GGUFValidationError
        validate_gguf_file(real)
    except GGUFValidationError as e:
        raise LLMError(f"gguf validation failed: {e}")
    except ImportError:
        # validator missing - fall back to magic only (should not happen)
        pass
    return real


def _extract_gguf_context_length(path: str) -> Optional[int]:
    """Try to read context length from GGUF KV without loading model. Returns None if not found."""
    try:
        from core.gguf_validator import validate_gguf_file
        # validate already parses but we need to capture it - re-parse lightly
        # Instead of duplicating parse, try to read known keys via quick scan
        import struct
        real = os.path.realpath(path)
        with open(real, "rb") as f:
            if f.read(4) != b"GGUF":
                return None
            f.read(4)  # version
            n_tensors = struct.unpack("<Q", f.read(8))[0]
            n_kv = struct.unpack("<Q", f.read(8))[0]
            if n_kv > 200_000:
                return None
            for _ in range(n_kv):
                key_len = struct.unpack("<Q", f.read(8))[0]
                if key_len > 8192:
                    return None
                key = f.read(key_len).decode("utf-8", errors="ignore")
                gtype = struct.unpack("<i", f.read(4))[0]
                if key.endswith("context_length"):
                    # expect uint32/uint64
                    if gtype == 4:  # UINT32
                        val = struct.unpack("<I", f.read(4))[0]
                        return int(val)
                    elif gtype == 10:  # UINT64
                        val = struct.unpack("<Q", f.read(8))[0]
                        return int(val)
                    elif gtype == 5:  # INT32
                        val = struct.unpack("<i", f.read(4))[0]
                        return int(val)
                    elif gtype == 11:
                        val = struct.unpack("<q", f.read(8))[0]
                        return int(val)
                # skip value
                # we need to skip correctly to stay in sync - use validator's logic simplified
                # For now, if not target key, we need generic skip. Implement minimal.
                if gtype == 0: f.seek(1, os.SEEK_CUR)
                elif gtype == 1: f.seek(1, os.SEEK_CUR)
                elif gtype == 2: f.seek(2, os.SEEK_CUR)
                elif gtype == 3: f.seek(2, os.SEEK_CUR)
                elif gtype == 4: f.seek(4, os.SEEK_CUR)
                elif gtype == 5: f.seek(4, os.SEEK_CUR)
                elif gtype == 6: f.seek(4, os.SEEK_CUR)
                elif gtype == 7: f.seek(1, os.SEEK_CUR)
                elif gtype == 8:
                    slen = struct.unpack("<Q", f.read(8))[0]
                    if slen > 10*1024*1024:
                        return None
                    f.seek(slen, os.SEEK_CUR)
                elif gtype == 9:
                    atype = struct.unpack("<i", f.read(4))[0]
                    alen = struct.unpack("<Q", f.read(8))[0]
                    if alen > 10*1024*1024:
                        return None
                    if atype == 8:
                        for __ in range(alen):
                            elen = struct.unpack("<Q", f.read(8))[0]
                            f.seek(elen, os.SEEK_CUR)
                    elif atype in (0,1,7): f.seek(alen*1, os.SEEK_CUR)
                    elif atype in (2,3): f.seek(alen*2, os.SEEK_CUR)
                    elif atype in (4,5,6): f.seek(alen*4, os.SEEK_CUR)
                    elif atype in (10,11,12): f.seek(alen*8, os.SEEK_CUR)
                    else: return None
                elif gtype == 10: f.seek(8, os.SEEK_CUR)
                elif gtype == 11: f.seek(8, os.SEEK_CUR)
                elif gtype == 12: f.seek(8, os.SEEK_CUR)
                else:
                    return None
    except Exception:
        return None
    return None


def _get_llama(path: str, n_ctx: int, n_threads: int, n_gpu: int, embedding: bool = False):
    # Validate and resolve
    real = _validate_gguf_path(path)
    # Clamp n_ctx to safe bounds and to file's declared context if available
    # Trains up to 262k now common (Qwen3, Llama3.1 etc.) — allow 131k, auto-scale
    n_ctx = int(n_ctx or DEFAULT_CONTEXT_WINDOW)
    n_ctx = max(512, min(262144, n_ctx))
    ctx_declared = _extract_gguf_context_length(real)
    if ctx_declared:
        # If model was trained for larger context and user left default, utilize more.
        # Keep user request if explicitly larger than default, but never exceed train.
        # This fixes "n_ctx_seq < n_ctx_train – full capacity not utilized"
        if ctx_declared > 32768 and n_ctx < 8192:
            # user still on old 4096 default while model supports 262k -> bump to 32k
            n_ctx = min(32768, ctx_declared)
        # Always clamp to train to avoid RoPE extrapolation issues
        n_ctx = min(n_ctx, max(512, ctx_declared))
        if n_ctx < ctx_declared:
            logger.info(f"GGUF train ctx {ctx_declared} > seq {n_ctx} – using {n_ctx} (increase gguf_n_ctx in Settings to utilize more, up to {ctx_declared})")
    # Auto n_batch scaling for large ctx
    # n_batch should be <= n_ctx and power-of-two friendly

    key = (real, n_ctx, int(n_threads or 0), int(n_gpu or 0), bool(embedding))
    with _GGUF_LOCK:
        if key in _GGUF_CACHE:
            return _GGUF_CACHE[key]

    try:
        from llama_cpp import Llama
    except ImportError as e:
        raise LLMError("llama-cpp-python not installed: pip install llama-cpp-python")

    nt = _gguf_threads(n_threads)
    # Adaptive n_batch: larger for large context = fewer llama_eval calls = faster
    # Balance RAM vs speed. For 262k context, 512 is too small (512 evals per 262k prompt)
    try:
        fsize = os.path.getsize(real)
        if n_ctx >= 32768:
            n_batch = 2048
        elif n_ctx >= 16384:
            n_batch = 1024
        elif n_ctx > 8192:
            n_batch = 512
        elif n_ctx > 4096:
            n_batch = 512
        else:
            n_batch = 512
        # Huge model + huge ctx on low RAM: cap
        if fsize > 12 * 1024**3 and n_ctx > 32768 and n_batch > 1024:
            n_batch = 1024
        if fsize > 20 * 1024**3 and n_batch > 512:
            n_batch = 512
    except:
        n_batch = 1024 if n_ctx >= 16384 else (512 if n_ctx > 4096 else 512)

    try:
        # Secure defaults: use_mmap True but validated, use_mlock False, verbose False
        # low_vram helps on constrained systems
        m = Llama(
            model_path=real,
            n_ctx=n_ctx,
            n_threads=nt,
            n_gpu_layers=int(n_gpu or 0),
            verbose=False,
            use_mmap=True,
            use_mlock=False,
            embedding=embedding,
            n_batch=n_batch,
            low_vram=True,
        )
    except Exception as e:
        raise LLMError(f"gguf load fail {e}")

    with _GGUF_LOCK:
        _GGUF_CACHE[key] = m
    return m


def clear_gguf_cache():
    with _GGUF_LOCK:
        _GGUF_CACHE.clear()


class GGUFClient(BaseLLMClient):
    def __init__(self, model_path: str, n_ctx: int = 16384, n_threads: int = 0, n_gpu_layers: int = 0, embedding_path: str = ""):
        self.path = (model_path or "").strip()
        self.n_ctx = n_ctx or DEFAULT_CONTEXT_WINDOW
        self.n_threads = n_threads
        self.n_gpu = n_gpu_layers
        self.emb_path = (embedding_path or model_path or "").strip()

    def _resolve_path(self, m: str) -> str:
        """Securely resolve GGUF path. m can be basename, full path, or empty.
        Returns absolute realpath. Never returns a directory."""
        import os

        m = (m or "").strip()
        # 1) m is absolute file
        if m and os.path.isabs(m) and os.path.isfile(m):
            return os.path.realpath(m)
        # 2) base directory from self.path
        base_dir = ""
        if self.path:
            rp = os.path.realpath(self.path)
            if os.path.isfile(rp):
                base_dir = os.path.dirname(rp)
            elif os.path.isdir(rp):
                base_dir = rp
            else:
                # self.path may be non-existent, try its dirname
                base_dir = os.path.dirname(self.path)

        if m and base_dir and os.path.isdir(base_dir):
            # try basename join
            cand = os.path.join(base_dir, os.path.basename(m))
            if os.path.isfile(cand):
                return os.path.realpath(cand)
            # try full m as relative join
            cand2 = os.path.join(base_dir, m)
            # prevent path traversal outside base_dir? We allow but resolve and check isfile
            # Still ensure final path is file
            if os.path.isfile(cand2):
                # Optional traversal guard: ensure realpath is still under base_dir or elsewhere but not sensitive?
                # For usability we allow any file, but validator will block non-GGUF
                return os.path.realpath(cand2)

        # 3) m itself is file (relative cwd)
        if m and os.path.isfile(m):
            return os.path.realpath(m)

        # 4) fallback to self.path if it's a file
        if self.path and os.path.isfile(self.path):
            return os.path.realpath(self.path)
        if self.path and os.path.isfile(os.path.realpath(self.path)):
            return os.path.realpath(self.path)

        # 5) if self.path is directory and m provided, try there
        if self.path and os.path.isdir(os.path.realpath(self.path)) and m:
            cand = os.path.join(os.path.realpath(self.path), os.path.basename(m))
            if os.path.isfile(cand):
                return os.path.realpath(cand)

        # 6) if self.path is directory and m empty, pick first valid GGUF in dir
        if not m and self.path and os.path.isdir(os.path.realpath(self.path)):
            import glob
            rp = os.path.realpath(self.path)
            g = glob.glob(os.path.join(rp, "*.gguf")) + glob.glob(os.path.join(rp, "*.GGUF"))
            for cand in sorted(g)[:50]:
                if os.path.isfile(cand):
                    try:
                        with open(cand, "rb") as fh:
                            if fh.read(4) == b"GGUF":
                                return os.path.realpath(cand)
                    except:
                        continue

        # fallback: return whichever exists, or m or self.path
        if m and os.path.isfile(os.path.realpath(m)):
            return os.path.realpath(m)
        return os.path.realpath(self.path) if self.path else (os.path.realpath(m) if m else "")

    def list_models(self) -> List[str]:
        import glob
        p = (self.path or "").strip()
        if not p:
            return []
        # Resolve to realpath to avoid symlink tricks
        try:
            rp = os.path.realpath(p)
        except:
            rp = p

        candidates: List[str] = []
        try:
            if os.path.isdir(rp):
                # Limit scanning to this directory non-recursive, max 200 files
                g = glob.glob(os.path.join(rp, "*.gguf"))
                g += glob.glob(os.path.join(rp, "*.GGUF"))
                # also handle case insensitive on Linux
                for cand in g[:200]:
                    if os.path.isfile(cand):
                        # quick magic check to filter non-GGUF
                        try:
                            with open(cand, "rb") as fh:
                                if fh.read(4) == b"GGUF":
                                    candidates.append(os.path.basename(cand))
                        except:
                            continue
                return sorted(set(candidates))
            if os.path.isfile(rp):
                d = os.path.dirname(rp)
                if not d or not os.path.isdir(d):
                    # single file case
                    if os.path.basename(rp).lower().endswith(".gguf"):
                        return [os.path.basename(rp)]
                    return []
                g = glob.glob(os.path.join(d, "*.gguf"))
                g += glob.glob(os.path.join(d, "*.GGUF"))
                for cand in g[:200]:
                    if os.path.isfile(cand):
                        try:
                            with open(cand, "rb") as fh:
                                if fh.read(4) == b"GGUF":
                                    candidates.append(os.path.basename(cand))
                        except:
                            continue
                if not candidates and os.path.basename(rp).lower().endswith(".gguf"):
                    candidates = [os.path.basename(rp)]
                return sorted(set(candidates)) if candidates else [os.path.basename(rp)] if os.path.basename(rp).lower().endswith(".gguf") else []
            # p is non-existent path but its dirname exists (e.g. user typed future path)
            d = os.path.dirname(p)
            if d and os.path.isdir(os.path.realpath(d)):
                g = glob.glob(os.path.join(os.path.realpath(d), "*.gguf"))
                g += glob.glob(os.path.join(os.path.realpath(d), "*.GGUF"))
                for cand in g[:200]:
                    if os.path.isfile(cand):
                        try:
                            with open(cand, "rb") as fh:
                                if fh.read(4) == b"GGUF":
                                    candidates.append(os.path.basename(cand))
                        except:
                            continue
                return sorted(set(candidates))
        except Exception:
            return []
        return []

    def get_context_window(self, m: str) -> int:
        # Fast path: try to read from GGUF header without loading model
        try:
            path = self._resolve_path(m)
            if path and os.path.isfile(path):
                cl = _extract_gguf_context_length(path)
                if cl and 512 <= cl <= 262144:
                    return int(cl)
        except:
            pass
        # Fall back to loading model (heavy) but cached
        try:
            path = self._resolve_path(m)
            if not path or not os.path.isfile(path):
                return self.n_ctx or DEFAULT_CONTEXT_WINDOW
            # Validate header first (quick)
            _validate_gguf_path(path)
            llama = _get_llama(path, self.n_ctx, self.n_threads, self.n_gpu, embedding=False)
            try:
                if hasattr(llama, "n_ctx"):
                    v = int(llama.n_ctx())
                    if 512 <= v <= 262144:
                        return v
            except:
                pass
            return self.n_ctx
        except:
            return self.n_ctx or DEFAULT_CONTEXT_WINDOW

    def chat_stream(self, m: str, msgs: List[Dict], temperature: float = 0.4, context_window: int = DEFAULT_CONTEXT_WINDOW) -> Generator[str, None, None]:
        path = self._resolve_path(m)
        # Validate before heavy load to give clear error
        _validate_gguf_path(path)
        llama = _get_llama(path, self.n_ctx, self.n_threads, self.n_gpu, embedding=False)
        mt = min(2048, max(256, context_window // 4))
        try:
            stream = llama.create_chat_completion(messages=msgs, temperature=temperature, max_tokens=mt, stream=True)
            for chunk in stream:
                try:
                    delta = chunk["choices"][0].get("delta", {})
                    piece = delta.get("content", "")
                    if piece:
                        yield piece
                except:
                    continue
        except Exception as e:
            raise LLMError(f"gguf chat fail {e}")

    def chat_json(self, m: str, msgs: List[Dict], schema: Dict[str, Any], temperature: float = 0.0) -> Optional[str]:
        path = self._resolve_path(m)
        _validate_gguf_path(path)
        llama = _get_llama(path, self.n_ctx, self.n_threads, self.n_gpu, embedding=False)
        try:
            out = llama.create_chat_completion(messages=msgs, temperature=temperature, max_tokens=2048, stream=False, response_format={"type": "json_object"})
            try:
                return out["choices"][0]["message"]["content"]
            except:
                return None
        except:
            try:
                txt = ""
                for p in self.chat_stream(m, msgs, temperature, context_window=self.n_ctx):
                    txt += p
                return txt if txt.strip() else None
            except Exception as e:
                raise LLMError(f"gguf json fail {e}")

    def embed(self, m: str, txts: List[str]) -> List[List[float]]:
        import os

        # Resolve path: prefer explicit m, then emb_path, then _resolve
        path = None
        if m and os.path.isfile(m):
            path = os.path.realpath(m)
        elif self.emb_path and os.path.isfile(self.emb_path):
            path = os.path.realpath(self.emb_path)
        else:
            # try resolve via _resolve_path
            cand = self._resolve_path(m)
            if cand and os.path.isfile(cand):
                path = cand
            elif self.emb_path:
                cand2 = self._resolve_path(self.emb_path)
                if cand2 and os.path.isfile(cand2):
                    path = cand2
        if not path or not os.path.isfile(path):
            raise LLMError(f"gguf embed model not found {path or m or self.emb_path}")
        _validate_gguf_path(path)
        llama = _get_llama(path, self.n_ctx, self.n_threads, self.n_gpu, embedding=True)
        out = []
        for t in txts:
            t = t[:8000]
            try:
                if hasattr(llama, "embed"):
                    v = llama.embed(t)
                    if isinstance(v, list) and v and isinstance(v[0], float):
                        out.append(v)
                    else:
                        out.append(list(v))
                elif hasattr(llama, "create_embedding"):
                    r = llama.create_embedding(input=t)
                    out.append(r["data"][0]["embedding"])
                else:
                    raise LLMError("embed not supported by llama_cpp")
            except Exception as e:
                raise LLMError(f"gguf embed fail {e}")
        return out


def get_client(ollama_host: str = "", gguf_model_path: str = "", backend: str = "ollama", n_ctx: int = 16384, n_threads: int = 0, n_gpu_layers: int = 0, embedding_path: str = "") -> BaseLLMClient:
    if backend == "gguf":
        return GGUFClient(gguf_model_path, n_ctx=n_ctx, n_threads=n_threads, n_gpu_layers=n_gpu_layers, embedding_path=embedding_path)
    return OllamaClient(normalize_host(ollama_host) if ollama_host else "http://localhost:11434")


def get_client_for_config(cfg) -> BaseLLMClient:
    if getattr(cfg, "llm_backend", "ollama") == "gguf":
        return GGUFClient(cfg.gguf_model_path, n_ctx=cfg.gguf_n_ctx, n_threads=cfg.gguf_n_threads, n_gpu_layers=cfg.gguf_n_gpu_layers, embedding_path=cfg.gguf_embedding_model_path or cfg.gguf_model_path)
    return OllamaClient(normalize_host(cfg.ollama_host) if cfg.ollama_host else "http://localhost:11434")


def ask(model: str, system_prompt: str, ctx: str, question: str, schema_model: type[BaseModel], client: Optional[BaseLLMClient] = None, ollama_host: str = "", max_retries: int = 1) -> Optional[BaseModel]:
    if client is None:
        client = get_client(ollama_host)
    schema = schema_model.model_json_schema()
    base = "\n\nEvery citation quote must be copied character-for-character from the provided context. Never paraphrase inside a quote field."
    for attempt in range(max_retries + 1):
        reminder = base if attempt == 0 else base + "\n\nRETRY: You previously failed to produce valid JSON matching the schema. Produce valid JSON this time. Every quote must be verbatim from the context. Do not invent."
        msgs = [{"role": "system", "content": system_prompt + reminder}, {"role": "user", "content": f"CONTEXT:\n{ctx}\n\nQUESTION:\n{question}"}]
        try:
            raw = client.chat_json(model, msgs, schema, temperature=0.0)
        except LLMError:
            return None
        if not raw:
            continue
        try:
            return schema_model.model_validate_json(raw)
        except:
            continue
    return None
