from __future__ import annotations

import json
from pathlib import Path


def empty() -> dict:
    return {"overview": {"story": "", "glossaryDivergences": []}, "nodes": {}, "pruned": []}


def load(run_dir: Path) -> dict:
    path = run_dir / "explanations.json"
    data = json.loads(path.read_text()) if path.exists() else empty()
    for key, value in empty().items():
        data.setdefault(key, value)
    return data


def merge(base: dict, fragment: dict) -> dict:
    base.setdefault("overview", {}).update(fragment.get("overview", {}))
    base.setdefault("nodes", {}).update(fragment.get("nodes", {}))
    if fragment.get("nodes"):
        base["pruned"] = [p for p in base.get("pruned", []) if p["id"] not in fragment["nodes"]]
    return base


def save(run_dir: Path, data: dict) -> None:
    (run_dir / "explanations.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
