from __future__ import annotations

from collections import deque
from typing import Dict, List, Set, Tuple


def caller_ids(node: dict) -> List[str]:
    return [caller["from"] for caller in node.get("callers", [])]


def link_ids(node: dict) -> List[str]:
    return [link["to"] for link in node.get("links", []) if "to" in link]


def entry_points(nodes: Dict[str, dict], upward: Set[str]) -> Tuple[List[str], List[str]]:
    roots = [i for i in upward if i in nodes and nodes[i].get("callersComputed") and not nodes[i].get("callers")]
    return (sorted(i for i in roots if not nodes[i].get("test")),
            sorted(i for i in roots if nodes[i].get("test")))


def impact_paths(changed: List[str], nodes: Dict[str, dict], entries: Set[str], limit: int = 10) -> Dict[str, dict]:
    result = {}
    for start in changed:
        previous = {start: None}
        queue = deque([start])
        found = []
        while queue:
            current = queue.popleft()
            if current in entries and current != start:
                found.append(current)
            for caller in caller_ids(nodes.get(current, {})):
                if caller not in previous:
                    previous[caller] = current
                    queue.append(caller)
        paths = []
        for entry in found:
            path = [entry]
            while previous[path[-1]] is not None:
                path.append(previous[path[-1]])
            paths.append(list(reversed(path)))
        paths.sort(key=lambda p: (len(p), p))
        result[start] = {"paths": paths[:limit], "omitted": max(0, len(paths) - limit)}
    return result


def parts(changed: List[str], nodes: Dict[str, dict]) -> List[List[str]]:
    changed_set = set(changed)
    parent = {i: i for i in changed}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    for i in changed:
        for other in link_ids(nodes[i]) + caller_ids(nodes[i]):
            if other in changed_set:
                union(i, other)
    for node in nodes.values():
        targets = [t for t in link_ids(node) if t in changed_set]
        for a, b in zip(targets, targets[1:]):
            union(a, b)
    groups: Dict[str, List[str]] = {}
    for i in changed:
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: (-len(g), changed.index(g[0])))


def signals(changed: List[str], nodes: Dict[str, dict], impact: Dict[str, dict]) -> Dict[str, dict]:
    changed_set = set(changed)
    result = {}
    for i in changed:
        node = nodes[i]
        change = node.get("change", {})
        linked = {o for o in link_ids(node) + caller_ids(node) if o in changed_set and o != i}
        result[i] = {
            "linesChanged": len(change.get("added", [])) + sum(len(b["text"]) for b in change.get("removed", [])),
            "new": change.get("status") == "added",
            "linkedChanges": len(linked),
            "onEntryPath": bool(impact.get(i, {}).get("paths")),
        }
    return result
