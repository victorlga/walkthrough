from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Set

from walkthrough import gitops
from walkthrough.diffparse import strip_prefix

EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class ReviewError(Exception):
    pass


def hunk_lines(diff: str) -> Dict[str, Set[int]]:
    lines: Dict[str, Set[int]] = {}
    path = None
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = strip_prefix(raw[4:])
        elif path and raw.startswith("@@"):
            match = HUNK.match(raw)
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            lines.setdefault(path, set()).update(range(start, start + count))
    return lines


def build_review(review: dict, anchorable: Dict[str, Set[int]]) -> dict:
    event = review.get("event")
    if event not in EVENTS:
        raise ReviewError(f"the verdict must be one of {', '.join(sorted(EVENTS))}, not {event!r}")
    inline, loose = [], []
    for comment in review.get("comments", []):
        text = str(comment.get("body", "")).strip()
        if not text:
            continue
        if comment["line"] in anchorable.get(comment["path"], set()):
            inline.append({"path": comment["path"], "line": comment["line"], "side": "RIGHT", "body": text})
        else:
            loose.append(f"`{comment['path']}:{comment['line']}`\n{text}")
    body = "\n\n".join(part for part in [str(review.get("body", "")).strip()] + loose if part)
    if event == "REQUEST_CHANGES" and not body and not inline:
        raise ReviewError("asking for changes needs a comment")
    return {"commit_id": review["head"], "event": event, "body": body, "comments": inline}


def load_review(path: Path) -> dict:
    review = json.loads(path.read_text())
    if review.get("walkthroughReview") != 1 or not review.get("pr"):
        raise ReviewError(f"{path} is not a walkthrough review block")
    return review


def post(review: dict, payload: dict) -> str:
    repo = Path(review["repoPath"])
    result = subprocess.run(["gh", "api", "--method", "POST", f"repos/{{owner}}/{{repo}}/pulls/{review['pr']}/reviews",
                             "--input", "-"], cwd=repo, input=json.dumps(payload), capture_output=True, text=True)
    if result.returncode != 0:
        raise ReviewError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout).get("html_url", "")


def anchorable_lines(review: dict) -> Dict[str, Set[int]]:
    diff = gitops.run_git(Path(review["repoPath"]), "diff", "--no-color", "--no-ext-diff", "-U3", review["base"], review["head"])
    return hunk_lines(diff)
