from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from walkthrough.markers import find_markers, name_index, neighbors, resolve

LEVELS = {"full", "short", "summary"}
SECTIONS = {"context", "before", "why", "steps", "impact", "relation", "syntax"}
REQUIRED = {
    ("full", "added"): ["context", "why", "steps", "impact"],
    ("full", "modified"): ["context", "before", "why", "steps", "impact"],
    ("full", "unchanged"): ["context", "steps", "relation"],
    ("short", "added"): ["context", "relation"],
    ("short", "modified"): ["context", "relation"],
    ("short", "unchanged"): ["context", "relation"],
}
STEP = re.compile(r"^\s*\d+[.)]\s+")


@dataclass
class Problem:
    id: str
    field: str
    marker: str
    reason: str

    def __str__(self) -> str:
        return f"{self.id} [{self.field}] {self.marker} {self.reason}"


def check_text(owner: str, field: str, text: str, lines: Optional[list], names: Dict[str, List[str]],
               prefer=()) -> List[Problem]:
    problems = []
    for marker in find_markers(text):
        if marker.kind == "lines":
            if lines is None:
                problems.append(Problem(owner, field, marker.raw, "line markers only work inside a function"))
            elif marker.start < lines[0] or marker.end > lines[1]:
                problems.append(Problem(owner, field, marker.raw,
                                        f"lines {marker.start}-{marker.end} are outside {lines[0]}-{lines[1]}"))
            continue
        found, candidates = resolve(marker.target, names, prefer)
        if found is None and candidates:
            problems.append(Problem(owner, field, marker.raw, f"is ambiguous: {', '.join(candidates)}"))
        elif found is None:
            problems.append(Problem(owner, field, marker.raw, "is not a function in the index"))
    return problems


def check_plan(index: dict, plan: dict, pruned: set, max_skeleton: int) -> List[Problem]:
    problems = []
    changed = set(index["changed"])
    skeleton = plan.get("skeleton", [])
    other = plan.get("other", [])
    roteiro = [i for part in plan.get("parts", []) for i in part.get("roteiro", [])]
    mechanical = set(plan.get("mechanical", {}).get("paths", []))
    if len(skeleton) > max_skeleton:
        problems.append(Problem("plan", "skeleton", "", f"has {len(skeleton)} functions, the maximum is {max_skeleton}"))
    for node_id in skeleton + other + roteiro:
        if node_id not in changed:
            problems.append(Problem("plan", "ids", node_id, "is not a changed function"))
    if set(roteiro) != set(skeleton):
        problems.append(Problem("plan", "parts", "", "the roteiro of the parts must list exactly the skeleton"))
    for node_id in set(skeleton) & set(other):
        problems.append(Problem("plan", "other", node_id, "is in the skeleton and in other"))
    for node_id in index["changed"]:
        covered = node_id in skeleton or node_id in other or index["nodes"][node_id]["path"] in mechanical
        if not covered and node_id not in pruned:
            problems.append(Problem("plan", "coverage", node_id, "changed function is not in the plan"))
    return problems


def validate(index: dict, plan: dict, explanations: dict, max_skeleton: int = 12) -> List[Problem]:
    nodes = index["nodes"]
    hunks = {h["id"] for h in index.get("hunks", [])}
    names = name_index(nodes)
    pruned = {p["id"] for p in explanations.get("pruned", [])}
    problems = check_plan(index, plan, pruned, max_skeleton)
    overview = explanations.get("overview", {})
    if not str(overview.get("story", "")).strip():
        problems.append(Problem("overview", "story", "", "the story is empty"))
    changed = set(index["changed"])
    problems += check_text("overview", "story", overview.get("story", ""), None, names, (changed,))
    for number, item in enumerate(overview.get("glossaryDivergences", [])):
        problems += check_text("overview", f"glossaryDivergences.{number}", item, None, names, (changed,))
    entries = explanations.get("nodes", {})
    for node_id, entry in entries.items():
        if node_id not in nodes and node_id not in hunks:
            problems.append(Problem(node_id, "id", "", "is neither a function nor a hunk in the index"))
            continue
        level = entry.get("level")
        if level not in LEVELS or (node_id in hunks and level != "summary"):
            problems.append(Problem(node_id, "level", str(level), "is not a valid level here"))
            continue
        if not str(entry.get("summary", "")).strip():
            problems.append(Problem(node_id, "summary", "", "the summary is empty"))
        lines = nodes[node_id]["lines"] if node_id in nodes else None
        prefer = (neighbors(nodes[node_id]), changed) if node_id in nodes else (changed,)
        problems += check_text(node_id, "summary", entry.get("summary", ""), lines, names, prefer)
        sections = entry.get("sections", {})
        for key in sections:
            if key not in SECTIONS:
                problems.append(Problem(node_id, "sections", key, "is not a known section"))
        if node_id in nodes:
            status = nodes[node_id]["change"]["status"]
            for key in REQUIRED.get((level, status), []):
                if not str(sections.get(key, "")).strip():
                    problems.append(Problem(node_id, "sections", "", f"missing section '{key}' for a {level} {status} explanation"))
        for key, text in sections.items():
            problems += check_text(node_id, key, text, lines, names, prefer)
        for line in str(sections.get("steps", "")).splitlines():
            if STEP.match(line) and not any(m.kind == "lines" for m in find_markers(line)):
                problems.append(Problem(node_id, "steps", line.strip(), "step without a line marker"))
    mechanical = set(plan.get("mechanical", {}).get("paths", []))
    for node_id in plan.get("skeleton", []):
        if node_id not in pruned and entries.get(node_id, {}).get("level") != "full":
            problems.append(Problem(node_id, "level", "", "skeleton functions need a full explanation"))
    for node_id in index["changed"]:
        exempt = node_id in pruned or nodes[node_id]["path"] in mechanical
        if not exempt and node_id not in entries:
            problems.append(Problem(node_id, "summary", "", "changed function has no explanation"))
    return problems


def prune(explanations: dict, problems: List[Problem]) -> List[Problem]:
    remaining = []
    nodes = explanations.setdefault("nodes", {})
    pruned = explanations.setdefault("pruned", [])
    for problem in problems:
        if problem.id in ("plan", "overview"):
            remaining.append(problem)
        elif problem.id in nodes:
            del nodes[problem.id]
            pruned.append({"id": problem.id, "reason": f"{problem.field}: {problem.marker} {problem.reason}".strip()})
        elif not any(p["id"] == problem.id for p in pruned):
            remaining.append(problem)
    return remaining
