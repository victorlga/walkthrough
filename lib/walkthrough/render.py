from __future__ import annotations

import html
import json
from pathlib import Path

from walkthrough import explanations as explanations_store
from walkthrough.config import SKILL_DIR

MAX_BYTES = 15_500_000
DOCUMENT_START = ('<!doctype html><html><head><meta charset="utf-8">'
                  '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                  '</head><body>')
EMPTY_PLAN = {"parts": [], "skeleton": [], "other": [], "mechanical": {"summary": "", "paths": []}}


def page_title(meta: dict) -> str:
    return f"{meta.get('label') or 'branch'} walkthrough"


def script_json(data) -> str:
    text = json.dumps(data, ensure_ascii=False)
    for raw, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(raw, escaped)
    return text


def trim(data: dict, max_bytes: int) -> int:
    nodes = data["index"]["nodes"]
    removable = sorted((n for n in nodes.values() if n.get("direction") != "seed"),
                       key=lambda n: (-(n.get("depth", 0) + n.get("up", 0)), n["id"]))
    removed = {}
    while removable and len(script_json(data).encode()) > max_bytes:
        size = max(1, len(removable) // 20)
        batch, removable = removable[:size], removable[size:]
        for node in batch:
            removed[node["id"]] = (node["path"], node["lines"][0])
            del nodes[node["id"]]
        for node in nodes.values():
            for link in node["links"]:
                if link.get("to") in removed:
                    link["path"], link["targetLine"] = removed[link.pop("to")]
            node["implementations"] = [i for i in node.get("implementations", []) if i in nodes]
    return len(removed)


def render(run_dir: Path, out: Path, mode: str = "local", lang: str = "pt", max_bytes: int = MAX_BYTES) -> dict:
    index = json.loads((run_dir / "index.json").read_text())
    plan_path = run_dir / "plan.json"
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else EMPTY_PLAN
    rules_path = SKILL_DIR / "references" / "explanation-format.md"
    data = {"index": index, "plan": plan, "explanations": explanations_store.load(run_dir),
            "rules": rules_path.read_text() if rules_path.exists() else "", "lang": lang}
    template = (SKILL_DIR / "templates" / "page.html").read_text()
    core = (SKILL_DIR / "templates" / "page-core.js").read_text()
    overhead = len(template.encode()) + len(core.encode()) + len(DOCUMENT_START) + 64
    trimmed = trim(data, max_bytes - overhead)
    data["index"].setdefault("truncated", {})["trimmedForSize"] = trimmed
    page = (template.replace("__TITLE__", html.escape(page_title(index["meta"])))
            .replace("__LANG__", lang)
            .replace("__PAGE_CORE__", core)
            .replace("__WALKTHROUGH_DATA__", script_json(data)))
    if mode == "local":
        page = DOCUMENT_START + page + "</body></html>"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return {"path": str(out), "bytes": len(page.encode()), "trimmed": trimmed}
