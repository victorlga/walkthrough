from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

MARKER = re.compile(r"\[\[([^\]\n]+)\]\]")
LINE_MARKER = re.compile(r"^L(\d+)(?:-L?(\d+))?$")


@dataclass(frozen=True)
class Marker:
    raw: str
    kind: str
    start: int = 0
    end: int = 0
    target: str = ""


def find_markers(text: str) -> List[Marker]:
    markers = []
    for match in MARKER.finditer(text or ""):
        inner = match.group(1).strip()
        line = LINE_MARKER.match(inner)
        if line:
            first = int(line.group(1))
            last = int(line.group(2)) if line.group(2) else first
            markers.append(Marker(raw=match.group(0), kind="lines", start=min(first, last), end=max(first, last)))
        else:
            markers.append(Marker(raw=match.group(0), kind="ref", target=inner))
    return markers


def name_index(nodes: Dict[str, dict]) -> Dict[str, List[str]]:
    index: Dict[str, set] = {}
    for node_id, node in nodes.items():
        for key in {node_id, node.get("name"), node.get("qualname")}:
            if key:
                index.setdefault(key, set()).add(node_id)
    return {key: sorted(ids) for key, ids in index.items()}


def resolve(target: str, index: Dict[str, List[str]]) -> Tuple[Optional[str], List[str]]:
    candidates = index.get(target, [])
    return (candidates[0] if len(candidates) == 1 else None), candidates
