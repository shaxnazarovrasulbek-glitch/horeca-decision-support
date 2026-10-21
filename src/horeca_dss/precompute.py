"""Pre-computed results for the default demo dataset.

The rolling-origin back-tests and the waste simulation are the slowest steps on a small cloud
server. For the default demo data (seed 42, 365 days, ending on the evaluation date), their
results are stored as JSON in ``data/precomputed`` and loaded instead of being recomputed.

Each file stores a fingerprint of the code that produced it, so stale files are ignored
automatically when the data generator or the models change.

    python scripts/precompute.py      # (re)create the files
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "data" / "precomputed"
_SOURCES = ["forecasting.py", "operations.py", "data/generator.py", "data/calendar.py",
            "data/catalog.py", "data/loader.py"]


def code_version() -> str:
    h = hashlib.md5()
    base = Path(__file__).resolve().parent
    for name in _SOURCES:
        h.update((base / name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def _encode(v):
    if isinstance(v, pd.DataFrame):
        dates = [c for c in v.columns if pd.api.types.is_datetime64_any_dtype(v[c])]
        return {"__df__": v.to_json(orient="split", date_format="iso", date_unit="us", index=False), "__dates__": dates}
    if isinstance(v, pd.Timestamp):
        return {"__ts__": v.isoformat()}
    if isinstance(v, tuple):
        return {"__tuple__": [_encode(x) for x in v]}
    if isinstance(v, list):
        return [_encode(x) for x in v]
    if isinstance(v, dict):
        return {k: _encode(x) for k, x in v.items()}
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _decode(v):
    if isinstance(v, dict):
        if "__df__" in v:
            df = pd.read_json(io.StringIO(v["__df__"]), orient="split", convert_dates=False)
            for c in v.get("__dates__", []):
                df[c] = pd.to_datetime(df[c])
            return df
        if "__ts__" in v:
            return pd.Timestamp(v["__ts__"])
        if "__tuple__" in v:
            return tuple(_decode(x) for x in v["__tuple__"])
        return {k: _decode(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_decode(x) for x in v]
    return v


def path(name: str, dataset_id: str) -> Path:
    return DIR / f"{dataset_id}__{name}.json"


def save(name: str, dataset_id: str, result: dict) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    p = path(name, dataset_id)
    p.write_text(json.dumps({"code_version": code_version(), "result": _encode(result)}), encoding="utf-8")
    return p


def load(name: str, dataset_id: str) -> dict | None:
    """The stored result, or None if there is no file or it was made by different code."""
    p = path(name, dataset_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("code_version") != code_version():
            return None
        return _decode(data["result"])
    except Exception:
        return None
