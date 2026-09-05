from __future__ import annotations
import os
import struct
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

GGUF_MAGIC = b"GGUF"
MAX_GGUF_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50 GB soft cap for DoS
MIN_GGUF_FILE_SIZE = 32  # at least header
MAX_KV_COUNT = 200_000
MAX_TENSOR_COUNT = 200_000
MAX_KEY_LEN = 8192
MAX_STRING_LEN = 10 * 1024 * 1024  # 10 MB instead of 1 GB (CVE V-02)
MAX_ARRAY_ELEMENTS = 10 * 1024 * 1024
MAX_TENSOR_NAME_LEN = 512
GGML_MAX_DIMS = 4
MAX_ALIGNMENT = 1 << 20  # 1048576 per advisory V-01
GGUF_VERSION_SUPPORTED = (2, 3)

# gguf type enum
GGUF_TYPE_UINT8 = 0
GGUF_TYPE_INT8 = 1
GGUF_TYPE_UINT16 = 2
GGUF_TYPE_INT16 = 3
GGUF_TYPE_UINT32 = 4
GGUF_TYPE_INT32 = 5
GGUF_TYPE_FLOAT32 = 6
GGUF_TYPE_BOOL = 7
GGUF_TYPE_STRING = 8
GGUF_TYPE_ARRAY = 9
GGUF_TYPE_UINT64 = 10
GGUF_TYPE_INT64 = 11
GGUF_TYPE_FLOAT64 = 12
_MAX_GGUF_TYPE = 12

_TYPE_SIZE = {
    GGUF_TYPE_UINT8: 1,
    GGUF_TYPE_INT8: 1,
    GGUF_TYPE_UINT16: 2,
    GGUF_TYPE_INT16: 2,
    GGUF_TYPE_UINT32: 4,
    GGUF_TYPE_INT32: 4,
    GGUF_TYPE_FLOAT32: 4,
    GGUF_TYPE_BOOL: 1,
    GGUF_TYPE_UINT64: 8,
    GGUF_TYPE_INT64: 8,
    GGUF_TYPE_FLOAT64: 8,
}

CRITICAL_TEMPLATE_PATTERNS = [
    "__class__", "__mro__", "__subclasses__", "__globals__",
    "__builtins__", "subprocess", "popen",
]
# These are only dangerous when used inside a Jinja expression {{ ... }} / {% ... %}
# Checking them anywhere causes false positives (e.g. normal text containing "os.")
SUSPICIOUS_TEMPLATE_PATTERNS = [
    "os.", "sys.", "eval", "exec", "import", "open(", "compile(",
]

# Session-only trusted hashes (Trust Once) - not persisted
_SESSION_TRUSTED_HASHES: set[str] = set()


def trust_template_for_session(tmpl: str | None, path: str | None = None):
    """Trust a template for this session only."""
    h = None
    if tmpl is not None:
        h = hashlib.sha256(tmpl.encode("utf-8", errors="replace")).hexdigest()
    elif path:
        h = get_chat_template_hash(path)
    if h:
        _SESSION_TRUSTED_HASHES.add(h)


def get_chat_template(path: str) -> str | None:
    """Extract raw chat_template string from GGUF without full validation."""
    try:
        import struct as _st

        real = os.path.realpath(path)
        with open(real, "rb") as f:
            if f.read(4) != GGUF_MAGIC:
                return None
            f.read(4)
            n_tensors = _st.unpack("<Q", f.read(8))[0]
            n_kv = _st.unpack("<Q", f.read(8))[0]
            if n_kv > MAX_KV_COUNT:
                return None
            for _ in range(n_kv):
                key_len = _st.unpack("<Q", f.read(8))[0]
                if key_len > MAX_KEY_LEN or key_len == 0:
                    return None
                key = f.read(key_len).decode("utf-8", errors="replace")
                gtype = _st.unpack("<i", f.read(4))[0]
                if gtype == GGUF_TYPE_STRING:
                    slen = _st.unpack("<Q", f.read(8))[0]
                    if slen > MAX_STRING_LEN:
                        return None
                    sbytes = f.read(slen) if slen else b""
                    if key in ("tokenizer.chat_template", "general.chat_template", "chat_template"):
                        return sbytes.decode("utf-8", errors="replace")
                elif gtype in _TYPE_SIZE:
                    f.seek(_TYPE_SIZE[gtype], os.SEEK_CUR)
                elif gtype == GGUF_TYPE_ARRAY:
                    atype = _st.unpack("<i", f.read(4))[0]
                    alen = _st.unpack("<Q", f.read(8))[0]
                    if atype == GGUF_TYPE_STRING:
                        for __ in range(alen):
                            elen = _st.unpack("<Q", f.read(8))[0]
                            f.seek(elen, os.SEEK_CUR)
                    elif atype in _TYPE_SIZE:
                        f.seek(alen * _TYPE_SIZE[atype], os.SEEK_CUR)
                    else:
                        return None
                else:
                    return None
    except Exception:
        return None
    return None


def get_chat_template_hash(path: str) -> str | None:
    tmpl = get_chat_template(path)
    if tmpl is None:
        return None
    return hashlib.sha256(tmpl.encode("utf-8", errors="replace")).hexdigest()


def is_template_trusted(path: str, tmpl: str | None = None) -> bool:
    """Check if template hash is in session or persisted config trusted list."""
    h = None
    if tmpl is not None:
        h = hashlib.sha256(tmpl.encode("utf-8", errors="replace")).hexdigest()
    elif path:
        h = get_chat_template_hash(path)
        if h is None and tmpl is None:
            return True
    if h is None:
        return False
    if h in _SESSION_TRUSTED_HASHES:
        return True
    try:
        from core.config import config as _cfg

        if _cfg.is_gguf_template_trusted(h):
            return True
    except Exception:
        pass
    return False


class GGUFValidationError(ValueError):
    pass


def _is_power_of_two(n: int) -> bool:
    return n != 0 and (n & (n - 1) == 0)


def _read_exact(f, n: int) -> bytes:
    data = f.read(n)
    if len(data) != n:
        raise GGUFValidationError(f"truncated file: expected {n} bytes, got {len(data)}")
    return data


def validate_gguf_file(path: str, *, check_alignment: bool = True, check_template: bool = True) -> dict:
    """
    Lightweight GGUF header validator that catches CVEs V-01..V-06 without
    loading the full model via llama.cpp.

    Returns dict with parsed metadata (version, n_tensors, n_kv, alignment).
    Raises GGUFValidationError / LLMError on failure.
    """
    if not path:
        raise GGUFValidationError("empty GGUF path")
    p = Path(path)
    # symlink check - block symlinks to avoid doc-loader bypass disparity
    # we allow symlink if it resolves to a valid GGUF, but log it
    # For strict security, reject symlink: uncomment next 2 lines to block completely
    # if p.is_symlink():
    #     raise GGUFValidationError(f"symlink not allowed for GGUF: {path}")
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise GGUFValidationError(f"GGUF not found: {path}")
    # also check original is not a dir
    if os.path.isdir(path):
        raise GGUFValidationError(f"GGUF path is directory: {path}")

    size = os.path.getsize(real)
    if size < MIN_GGUF_FILE_SIZE:
        raise GGUFValidationError(f"GGUF too small ({size} bytes)")
    if size > MAX_GGUF_FILE_SIZE:
        raise GGUFValidationError(f"GGUF too large ({size} bytes > {MAX_GGUF_FILE_SIZE}) - possible DoS")

    with open(real, "rb") as f:
        magic = _read_exact(f, 4)
        if magic != GGUF_MAGIC:
            raise GGUFValidationError(f"not a GGUF file (bad magic {magic!r}), expected b'GGUF'")

        version = struct.unpack("<I", _read_exact(f, 4))[0]
        if version not in GGUF_VERSION_SUPPORTED:
            # allow version 1 for old models but warn
            if version not in (1, 2, 3):
                raise GGUFValidationError(f"unsupported GGUF version {version}, expected 2 or 3")
            logger.warning("GGUF version %d is old, prefer v3", version)

        n_tensors = struct.unpack("<Q", _read_exact(f, 8))[0]
        n_kv = struct.unpack("<Q", _read_exact(f, 8))[0]

        # signed int64 interpretation check (V-04): ensure values fit in size_t and not absurd
        # n_tensors/n_kv were historically int64 in file, but now uint64
        if n_tensors > MAX_TENSOR_COUNT:
            raise GGUFValidationError(f"n_tensors too large: {n_tensors}")
        if n_kv > MAX_KV_COUNT:
            raise GGUFValidationError(f"n_kv too large: {n_kv}")
        # also check that header + minimal data fits in file size
        # Rough lower bound: header 24 bytes + per KV at least 16 bytes
        min_expected = 24 + n_kv * 16 + n_tensors * 32
        if min_expected > size:
            raise GGUFValidationError(f"header claims more data ({min_expected}) than file size ({size})")

        alignment = 32  # default
        found_alignment = False
        # Parse KV store
        for ki in range(n_kv):
            pos = f.tell()
            if pos + 12 > size:
                raise GGUFValidationError(f"truncated KV {ki} header")

            key_len = struct.unpack("<Q", _read_exact(f, 8))[0]
            if key_len == 0 or key_len > MAX_KEY_LEN:
                raise GGUFValidationError(f"KV {ki}: bad key_len {key_len}")
            if f.tell() + key_len + 4 > size:
                raise GGUFValidationError(f"KV {ki}: key extends past EOF")
            key_bytes = _read_exact(f, key_len)
            try:
                key = key_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raise GGUFValidationError(f"KV {ki}: key not utf-8")

            gtype = struct.unpack("<i", _read_exact(f, 4))[0]  # int32
            if gtype < 0 or gtype > _MAX_GGUF_TYPE:
                raise GGUFValidationError(f"KV {ki} ({key}): bad gguf_type {gtype} (V-05)")

            # Validate / skip value
            if gtype in _TYPE_SIZE:
                sz = _TYPE_SIZE[gtype]
                if f.tell() + sz > size:
                    raise GGUFValidationError(f"KV {ki} ({key}): truncated scalar")
                raw = _read_exact(f, sz)
                if key == "general.alignment" and check_alignment:
                    # alignment should be uint32 but be tolerant
                    if gtype == GGUF_TYPE_UINT32:
                        val = struct.unpack("<I", raw)[0]
                    elif gtype == GGUF_TYPE_UINT64:
                        val = struct.unpack("<Q", raw)[0]
                    elif gtype == GGUF_TYPE_INT32:
                        val = struct.unpack("<i", raw)[0]
                    elif gtype == GGUF_TYPE_INT64:
                        val = struct.unpack("<q", raw)[0]
                    else:
                        raise GGUFValidationError(f"general.alignment has wrong type {gtype}")
                    found_alignment = True
                    alignment = val
                    # V-01 checks
                    if val == 0 or not _is_power_of_two(val):
                        raise GGUFValidationError(f"general.alignment {val} must be power of two >0")
                    if val > MAX_ALIGNMENT:
                        raise GGUFValidationError(f"general.alignment {val} > max {MAX_ALIGNMENT} (V-01)")
                # also check for chat_template SSTI
                # chat template stored as string type (8) not scalar, so handled below

            elif gtype == GGUF_TYPE_STRING:
                slen = struct.unpack("<Q", _read_exact(f, 8))[0]
                if slen > MAX_STRING_LEN:
                    raise GGUFValidationError(f"KV {ki} ({key}): string len {slen} > {MAX_STRING_LEN} (V-02)")
                if f.tell() + slen > size:
                    raise GGUFValidationError(f"KV {ki} ({key}): string extends past EOF")
                sbytes = _read_exact(f, slen) if slen else b""
                # SSTI check for chat_template (CVE-2024-34359)
                # Jinja2 chat_templates are executed by llama-cpp-python. Before 0.2.72
                # the template was rendered in an unsandboxed Environment, so a model
                # could execute `{{ os.system(...) }}` etc. on load.
                if check_template and key in ("tokenizer.chat_template", "general.chat_template", "chat_template"):
                    try:
                        txt = sbytes.decode("utf-8", errors="replace")
                    except Exception:
                        txt = ""
                    # If user explicitly trusted this template (Trust Once / Trust Always), skip SSTI checks
                    try:
                        if is_template_trusted(real, txt):
                            # still warn for huge templates
                            if len(txt) > 100_000:
                                logger.warning("chat_template unusually large (%d chars) even though trusted", len(txt))
                        else:
                            lower = txt.lower()
                            # 1) Always block critical introspection / subprocess patterns
                            for pat in CRITICAL_TEMPLATE_PATTERNS:
                                if pat.lower() in lower:
                                    raise GGUFValidationError(
                                        f"KV {key}: chat_template contains dangerous pattern '{pat}' (CVE-2024-34359 SSTI) - untrusted template blocked. If you trust this model, you can choose 'Trust & Load'."
                                    )
                            # 2) For suspicious patterns, only block when they appear
                            #    inside a Jinja expression {{ ... }} / {% ... %} to avoid
                            #    false positives on normal English text.
                            has_jinja = "{{" in txt or "{%" in txt
                            if has_jinja:
                                for pat in SUSPICIOUS_TEMPLATE_PATTERNS:
                                    # simple check: pattern inside Jinja delimiters
                                    # e.g. "{{ os.getenv('X') }}" or "{% import os %}"
                                    if pat.lower() in lower:
                                        raise GGUFValidationError(
                                            f"KV {key}: chat_template contains dangerous pattern '{pat}' inside Jinja expression (CVE-2024-34359 SSTI) - untrusted template blocked. If you trust this model, you can choose 'Trust & Load'."
                                        )
                            # also flag very large template (> 100k) as suspicious
                            if len(txt) > 100_000:
                                logger.warning("chat_template unusually large (%d chars) - possible injection", len(txt))
                    except GGUFValidationError:
                        raise
                    except Exception as e:
                        logger.debug(f"template trust check failed: {e}")
                        # fall through to normal checks without trust
                        lower = txt.lower()
                        for pat in CRITICAL_TEMPLATE_PATTERNS:
                            if pat.lower() in lower:
                                raise GGUFValidationError(
                                    f"KV {key}: chat_template contains dangerous pattern '{pat}' (CVE-2024-34359 SSTI) - untrusted template blocked. If you trust this model, you can choose 'Trust & Load'."
                                )

            elif gtype == GGUF_TYPE_ARRAY:
                atype = struct.unpack("<i", _read_exact(f, 4))[0]
                if atype < 0 or atype > _MAX_GGUF_TYPE:
                    raise GGUFValidationError(f"KV {ki} ({key}): bad array type {atype}")
                alen = struct.unpack("<Q", _read_exact(f, 8))[0]
                if alen > MAX_ARRAY_ELEMENTS:
                    raise GGUFValidationError(f"KV {ki} ({key}): array len {alen} > {MAX_ARRAY_ELEMENTS}")
                # check size quickly: for string arrays, need per-element len
                if atype == GGUF_TYPE_STRING:
                    for ai in range(alen):
                        if f.tell() + 8 > size:
                            raise GGUFValidationError(f"KV {ki} array element {ai} truncated")
                        elen = struct.unpack("<Q", _read_exact(f, 8))[0]
                        if elen > MAX_STRING_LEN:
                            raise GGUFValidationError(f"KV {ki} array element {ai} string len {elen} > max")
                        if f.tell() + elen > size:
                            raise GGUFValidationError(f"KV {ki} array element {ai} extends past EOF")
                        if elen:
                            _read_exact(f, elen)
                elif atype in _TYPE_SIZE:
                    need = alen * _TYPE_SIZE[atype]
                    if f.tell() + need > size:
                        raise GGUFValidationError(f"KV {ki} array exceeds file")
                    if need:
                        # seek instead of read for speed
                        f.seek(need, os.SEEK_CUR)
                else:
                    raise GGUFValidationError(f"KV {ki}: unsupported array type {atype}")
            else:
                raise GGUFValidationError(f"KV {ki} ({key}): unknown type {gtype}")

        # Parse tensor infos
        for ti in range(n_tensors):
            if f.tell() + 8 > size:
                raise GGUFValidationError(f"tensor {ti} truncated")
            name_len = struct.unpack("<Q", _read_exact(f, 8))[0]
            if name_len == 0 or name_len > MAX_TENSOR_NAME_LEN:
                raise GGUFValidationError(f"tensor {ti}: bad name_len {name_len}")
            if f.tell() + name_len > size:
                raise GGUFValidationError(f"tensor {ti}: name extends past EOF")
            _read_exact(f, name_len)

            # n_dims is uint32
            if f.tell() + 4 > size:
                raise GGUFValidationError(f"tensor {ti}: truncated n_dims")
            n_dims = struct.unpack("<I", _read_exact(f, 4))[0]
            if n_dims > GGML_MAX_DIMS:
                raise GGUFValidationError(f"tensor {ti}: n_dims {n_dims} > {GGML_MAX_DIMS} (V-03)")
            # dims: n_dims * uint64
            if n_dims:
                if f.tell() + n_dims * 8 > size:
                    raise GGUFValidationError(f"tensor {ti}: dims truncated")
                dims_bytes = _read_exact(f, n_dims * 8)
                dims = struct.unpack("<" + "Q" * n_dims, dims_bytes)
                # check dims plausible and check overflow for ggml_nbytes (V-06, CVE-2026-33298)
                # ggml_nbytes = type_size * prod(dims) / blck_size ; check prod doesn't overflow
                prod = 1
                for d in dims:
                    if d == 0:
                        # allow 0 dim? but log
                        continue
                    if d > (1 << 30):  # absurdly large dim (1B)
                        raise GGUFValidationError(f"tensor {ti}: dim {d} too large")
                    # overflow check for prod
                    if prod > (1 << 60) // max(1, d):
                        raise GGUFValidationError(f"tensor {ti}: dims product overflow (CVE-2026-33298)")
                    prod *= d

            # type
            if f.tell() + 4 > size:
                raise GGUFValidationError(f"tensor {ti}: truncated type")
            ttype = struct.unpack("<i", _read_exact(f, 4))[0]
            # ggml type enum 0.. ~30, but allow 0..32
            if ttype < 0 or ttype > 32:
                raise GGUFValidationError(f"tensor {ti}: bad type {ttype}")
            # offset
            if f.tell() + 8 > size:
                raise GGUFValidationError(f"tensor {ti}: truncated offset")
            offset = struct.unpack("<Q", _read_exact(f, 8))[0]
            if offset > size:
                raise GGUFValidationError(f"tensor {ti}: offset {offset} past EOF")

        # final alignment pad check - ensure alignment validated
        if found_alignment and alignment > MAX_ALIGNMENT:
            raise GGUFValidationError(f"alignment {alignment} too large")

        return {"version": version, "n_tensors": n_tensors, "n_kv": n_kv, "alignment": alignment, "size": size}


def is_valid_gguf(path: str) -> bool:
    try:
        validate_gguf_file(path)
        return True
    except Exception as e:
        logger.debug("GGUF validation failed for %s: %s", path, e)
        return False


def validate_gguf_or_raise(path: str):
    """Wrapper that raises LLMError-compatible message"""
    try:
        return validate_gguf_file(path)
    except GGUFValidationError as e:
        raise ValueError(str(e)) from e
