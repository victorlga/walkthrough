from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$")


@dataclass
class RemovedBlock:
    after: int
    old_start: int
    lines: List[str] = field(default_factory=list)


@dataclass
class FileDiff:
    path: str
    old_path: Optional[str] = None
    status: str = "modified"
    added: List[int] = field(default_factory=list)
    removed: List[RemovedBlock] = field(default_factory=list)

    @property
    def removed_count(self) -> int:
        return sum(len(block.lines) for block in self.removed)


def strip_prefix(value: str) -> Optional[str]:
    value = value.split("\t")[0]
    if value == "/dev/null":
        return None
    return value[2:] if value[:2] in ("a/", "b/") else value


def parse_diff(text: str) -> List[FileDiff]:
    files: List[FileDiff] = []
    current: Optional[FileDiff] = None
    block: Optional[RemovedBlock] = None
    old_from_header: Optional[str] = None
    new_line = 0

    def flush():
        if current is not None and block is not None and block.lines:
            current.removed.append(block)

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            flush()
            block = None
            header = HEADER.match(raw)
            current = FileDiff(path=header.group(2) if header else "")
            files.append(current)
            old_from_header = None
            continue
        if current is None:
            continue
        if block is None and raw.startswith("new file mode"):
            current.status = "added"
        elif block is None and raw.startswith("deleted file mode"):
            current.status = "deleted"
        elif block is None and raw.startswith("rename from "):
            current.old_path = raw[len("rename from "):]
            current.status = "renamed"
        elif block is None and raw.startswith("rename to "):
            current.path = raw[len("rename to "):]
        elif block is None and raw.startswith("Binary files "):
            current.status = "binary"
        elif block is None and raw.startswith("--- "):
            old_from_header = strip_prefix(raw[4:])
        elif block is None and raw.startswith("+++ "):
            current.path = strip_prefix(raw[4:]) or old_from_header or current.path
        elif raw.startswith("@@"):
            flush()
            match = HUNK.match(raw)
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            block = RemovedBlock(after=new_start if new_count == 0 else new_start - 1,
                                 old_start=int(match.group(1)))
            new_line = new_start
        elif block is not None and raw.startswith("-"):
            block.lines.append(raw[1:])
        elif block is not None and raw.startswith("+"):
            current.added.append(new_line)
            new_line += 1
    flush()
    return files
