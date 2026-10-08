from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

KIND_NAMES = {5: "class", 6: "method", 7: "property", 8: "field", 9: "constructor", 10: "enum",
              11: "interface", 12: "function", 13: "variable", 14: "constant", 22: "enum-member",
              23: "struct"}
PURE_CONTAINERS = {1, 2, 3, 4}
NODE_CONTAINERS = {5, 10, 11, 23}


@dataclass
class Candidate:
    name: str
    qualname: str
    kind: str
    kind_number: int
    start: int
    end: int
    sel_line: int
    sel_char: int
    depth: int
    parent: Optional[str]
    id: str = ""


def line_span(rng: dict) -> tuple:
    start0 = rng["start"]["line"]
    end0 = rng["end"]["line"]
    if rng["end"]["character"] == 0 and end0 > start0:
        end0 -= 1
    return start0 + 1, end0 + 1


def make_candidate(symbol: dict, qualname: str, depth: int, parent: Optional[str]) -> Candidate:
    rng = symbol.get("range") or symbol["location"]["range"]
    sel = symbol.get("selectionRange") or rng
    start, end = line_span(rng)
    kind = symbol.get("kind", 0)
    return Candidate(name=symbol["name"].strip(), qualname=qualname, kind=KIND_NAMES.get(kind, "other"),
                     kind_number=kind, start=start, end=end, sel_line=sel["start"]["line"],
                     sel_char=sel["start"]["character"], depth=depth, parent=parent)


def node_candidates(symbols: list) -> List[Candidate]:
    out: List[Candidate] = []

    def visit(items, prefix: str, depth: int, parent: Optional[str]):
        for symbol in items or []:
            kind = symbol.get("kind", 0)
            if kind in PURE_CONTAINERS:
                visit(symbol.get("children"), prefix, depth, parent)
                continue
            name = symbol["name"].strip()
            if "location" in symbol and symbol.get("containerName"):
                qualname, level = f"{symbol['containerName']}.{name}", 1
            else:
                qualname, level = (f"{prefix}.{name}" if prefix else name), depth
            out.append(make_candidate(symbol, qualname, level, parent))
            if kind in NODE_CONTAINERS:
                visit(symbol.get("children"), qualname, depth + 1, qualname)

    visit(symbols, "", 0, None)
    return out


def assign_ids(path: str, candidates: List[Candidate]) -> Dict[str, Candidate]:
    counts = Counter(c.qualname for c in candidates)
    by_id: Dict[str, Candidate] = {}
    for candidate in candidates:
        suffix = f":{candidate.start}" if counts[candidate.qualname] > 1 else ""
        candidate.id = f"{path}#{candidate.qualname}{suffix}"
        by_id[candidate.id] = candidate
    return by_id


def innermost(candidates: List[Candidate], line: int) -> Optional[Candidate]:
    containing = [c for c in candidates if c.start <= line <= c.end]
    if not containing:
        return None
    return max(containing, key=lambda c: (c.depth, -(c.end - c.start)))


def include_leading_comments(candidates: List[Candidate], lines: List[str], prefixes: tuple) -> None:
    if not prefixes:
        return
    for candidate in candidates:
        line = candidate.start - 1
        while line >= 1 and lines[line - 1].strip().startswith(prefixes) and not any(
                other is not candidate and other.start <= line <= other.end
                and not (other.start <= candidate.start and candidate.end <= other.end) for other in candidates):
            line -= 1
        candidate.start = line + 1
