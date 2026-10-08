from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

from walkthrough import gitops
from walkthrough.config import Config, Language
from walkthrough.diffparse import FileDiff, RemovedBlock, parse_diff
from walkthrough.graph import entry_points, impact_paths, parts, signals
from walkthrough.lsp import LspError, LspServer, uri_to_path
from walkthrough.symbols import Candidate, assign_ids, include_leading_comments, innermost, node_candidates
from walkthrough.tokens import decode_semantic_tokens, linkable, regex_tokens


@dataclass
class Caps:
    max_nodes: int = 1500
    max_down: int = 8
    max_up: int = 12
    impact_paths: int = 10


EXPANDING_KINDS = {"function", "method", "constructor", "other", "toplevel"}
DATA_MEMBER_KINDS = {"property", "field", "enum-member"}


class RootLost(Exception):
    pass


def external_package(uri: str) -> str:
    if uri.startswith(("jar:", "zipfile:")):
        jar = uri.split("::")[0].split("!")[0]
        return Path(unquote(urlparse(jar.replace("jar:", "", 1)).path)).stem
    path = str(uri_to_path(uri) or uri)
    if "/stdlib/" in path and "typeshed" in path:
        return "stdlib"
    if "/node_modules/" in path:
        rest = path.split("/node_modules/", 1)[1].split("/")
        return "/".join(rest[:2]) if rest[0].startswith("@") else rest[0]
    for marker in ("/site-packages/", "/dist-packages/"):
        if marker in path:
            return path.split(marker, 1)[1].split("/")[0]
    return Path(path).parent.name


def indent_of(line: str) -> int:
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def block_around(text: List[str], first: int, last: int, margin: int = 20, limit: int = 80) -> Tuple[int, int]:
    count = len(text)

    def blank(number: int) -> bool:
        return not text[number - 1].strip()

    def inside(number: int) -> bool:
        return not blank(number) and (indent_of(text[number - 1]) > 0 or text[number - 1].lstrip()[:1] in ")]}")

    start, end = max(1, first), min(count, last)
    while start > 1 and (not blank(start - 1) or (start > 2 and inside(start) and not blank(start - 2))):
        start -= 1
    while end < count and (not blank(end + 1) or (end + 2 <= count and inside(end + 2))):
        end += 1
    if end - start + 1 > limit:
        start, end = max(start, first - margin), min(end, last + margin)
    return start, end


def split_lines(text: str) -> List[str]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


class Indexer:
    def __init__(self, root: Path, base_sha: str, config: Config, caps: Caps, skip_languages, log):
        self.root = root.resolve()
        self.base_sha = base_sha
        self.config = config
        self.caps = caps
        self.skip = set(skip_languages)
        self.log = log or (lambda message: None)
        self.repo_files = gitops.repo_files(self.root)
        self.servers: Dict[Tuple[str, Path], LspServer] = {}
        self.restarted: set = set()
        self.lost: Dict[Tuple[str, Path], str] = {}
        self.lines_cache: Dict[str, List[str]] = {}
        self.candidates_cache: Dict[str, List[Candidate]] = {}
        self.tokens_cache: Dict[str, list] = {}
        self.known: Dict[str, Candidate] = {}
        self.path_by_id: Dict[str, str] = {}
        self.diffs: Dict[str, FileDiff] = {}
        self.files: Dict[str, dict] = {}
        self.nodes: Dict[str, dict] = {}
        self.changed_set: set = set()
        self.max_nodes_hit = False

    def relative(self, path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        try:
            rel = path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return None
        return rel if rel in self.repo_files else None

    def lines(self, rel: str) -> List[str]:
        if rel not in self.lines_cache:
            self.lines_cache[rel] = split_lines((self.root / rel).read_text(errors="replace"))
        return self.lines_cache[rel]

    def language(self, rel: str) -> Optional[Language]:
        language = self.config.language_for(rel)
        if language is None or language.name in self.skip:
            return None
        return language

    def project_root(self, rel: str, language: Language) -> Path:
        directory = (self.root / rel).parent
        while True:
            if any((directory / marker).exists() for marker in language.root_markers):
                return directory
            if directory == self.root or directory.parent == directory:
                return self.root
            directory = directory.parent

    def key(self, rel: str) -> Optional[Tuple[str, Path]]:
        language = self.language(rel)
        if language is None or not (self.root / rel).is_file():
            return None
        key = (language.name, self.project_root(rel, language))
        return None if key in self.lost else key

    def server(self, key: Tuple[str, Path]) -> LspServer:
        if key not in self.servers:
            language = self.config.languages[key[0]]
            server = LspServer(list(language.command), key[1], language.resolved_initialization_options())
            self.log(f"starting {key[0]} server at {key[1]}")
            try:
                server.start()
            except LspError as error:
                server.stop()
                self.lost[key] = str(error)
                raise RootLost(str(error))
            self.servers[key] = server
        return self.servers[key]

    def call(self, rel: str, operation: Callable[[LspServer, Path], object]):
        key = self.key(rel)
        if key is None:
            raise RootLost(rel)
        absolute = self.root / rel
        for attempt in (1, 2):
            try:
                server = self.server(key)
                server.open(absolute, self.config.language_id(rel))
                return operation(server, absolute)
            except LspError as error:
                old = self.servers.pop(key, None)
                if old is not None:
                    old.stop()
                if attempt == 2 or key in self.restarted:
                    self.lost[key] = str(error)
                    raise RootLost(str(error))
                self.restarted.add(key)
                self.log(f"restarting {key[0]} server after: {error}")

    def candidates(self, rel: str) -> List[Candidate]:
        if rel not in self.candidates_cache:
            try:
                symbols = self.call(rel, lambda server, path: server.document_symbols(path))
            except RootLost:
                symbols = []
            found = [c for c in node_candidates(symbols) if not self.is_alias(rel, c)]
            assign_ids(rel, found)
            language = self.config.language_for(rel)
            include_leading_comments(found, self.lines(rel), language.line_comment if language else ())
            for candidate in found:
                self.known[candidate.id] = candidate
                self.path_by_id[candidate.id] = rel
            self.candidates_cache[rel] = found
        return self.candidates_cache[rel]

    def is_alias(self, rel: str, candidate: Candidate) -> bool:
        if candidate.kind_number not in (13, 14):
            return False
        try:
            locations = self.call(rel, lambda s, p: s.definition(p, candidate.sel_line, candidate.sel_char))
        except RootLost:
            return False
        if not locations:
            return False
        target = uri_to_path(locations[0].uri)
        return target != (self.root / rel).resolve() or locations[0].line0 != candidate.sel_line

    def node_at(self, rel: str, line: int) -> Optional[Candidate]:
        return innermost(self.candidates(rel), line)

    def toplevel_at(self, rel: str, line: int) -> Candidate:
        node_id = f"{rel}@{line}"
        if node_id not in self.known:
            name = f"{Path(rel).name}:{line}"
            self.known[node_id] = Candidate(name=name, qualname=name, kind="toplevel", kind_number=0,
                                            start=max(1, line - 6), end=min(len(self.lines(rel)), line + 6),
                                            sel_line=line - 1, sel_char=0, depth=0, parent=None, id=node_id)
            self.path_by_id[node_id] = rel
        return self.known[node_id]

    def change_owner(self, candidates: List[Candidate], owner: Optional[Candidate]) -> Optional[Candidate]:
        if owner is None or owner.kind not in DATA_MEMBER_KINDS or not owner.parent:
            return owner
        return next((c for c in candidates if c.qualname == owner.parent), owner)

    def block_owner(self, rel: str, candidates: List[Candidate], block: RemovedBlock, added: Set[int]) -> Optional[Candidate]:
        before = innermost(candidates, block.after) if block.after else None
        following = innermost(candidates, block.after + 1)
        if before is not None and before == following:
            return before
        if following is not None and block.after + 1 in added:
            return following
        if before is not None and block.after in added:
            return before
        depth = min((indent_of(line) for line in block.lines if line.strip()), default=0)
        text = self.lines(rel)
        for owner in (before, following):
            if owner is not None and owner.start <= len(text) and depth > indent_of(text[owner.start - 1]):
                return owner
        return None

    def find_changes(self) -> Tuple[List[str], List[dict]]:
        changed: List[str] = []
        hunks: List[dict] = []
        for rel, diff in self.diffs.items():
            if self.files[rel]["generated"] or diff.status == "binary":
                continue
            candidates = self.candidates(rel) if self.key(rel) else []
            text = self.lines(rel) if diff.status != "deleted" and (self.root / rel).is_file() else []
            owners: Dict[str, Candidate] = {}
            loose_added: List[int] = []
            loose_blocks: List[RemovedBlock] = []
            for number in diff.added:
                owner = self.change_owner(candidates, innermost(candidates, number))
                if owner:
                    owners[owner.id] = owner
                elif number <= len(text) and text[number - 1].strip():
                    loose_added.append(number)
            for block in diff.removed:
                owner = self.change_owner(candidates, self.block_owner(rel, candidates, block, set(diff.added)))
                if owner:
                    owners[owner.id] = owner
                elif any(line.strip() for line in block.lines):
                    loose_blocks.append(block)
            changed.extend(c.id for c in sorted(owners.values(), key=lambda c: c.start))
            if loose_added or loose_blocks:
                hunks.extend(self.make_hunks(rel, text, loose_added, loose_blocks))
        return changed, hunks

    def make_hunks(self, rel: str, text: List[str], added: List[int], blocks: List[RemovedBlock]) -> List[dict]:
        events = sorted([(float(n), n) for n in added] + [(b.after + 0.5, b) for b in blocks], key=lambda e: e[0])
        groups: List[list] = []
        for event in events:
            if groups and event[0] - groups[-1][-1][0] <= 3:
                groups[-1].append(event)
            else:
                groups.append([event])
        added_set = set(added)
        spans: List[list] = []
        for group in groups:
            if text:
                low = max(1, int(group[0][0]))
                high = min(len(text), max(low, int(group[-1][0] + 0.5)))
                spans.append([*block_around(text, low, high), group])
            else:
                spans.append([0, 0, group])
        merged: List[list] = []
        for span in spans:
            if merged and text and span[0] <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], span[1])
                merged[-1][2] = merged[-1][2] + span[2]
            else:
                merged.append(span)
        hunks = []
        for first, last, group in merged:
            group_blocks = [item for _, item in group if isinstance(item, RemovedBlock)]
            lines: List[dict] = []
            if not text:
                for block in group_blocks:
                    lines.extend({"n": None, "kind": "del", "text": t} for t in block.lines)
            else:
                by_after: Dict[int, List[str]] = {}
                for block in group_blocks:
                    by_after.setdefault(block.after, []).extend(block.lines)
                for number in range(first, last + 1):
                    lines.extend({"n": None, "kind": "del", "text": t} for t in by_after.pop(number - 1, []))
                    lines.append({"n": number, "kind": "add" if number in added_set else "ctx", "text": text[number - 1]})
                for after in sorted(by_after):
                    lines.extend({"n": None, "kind": "del", "text": t} for t in by_after[after])
            start = next((line["n"] for line in lines if line["kind"] == "add"), group_blocks[0].after if group_blocks else 0)
            hunks.append({"id": f"{rel}@{start}", "path": rel, "lines": lines})
        return hunks

    def change_for(self, rel: str, candidate: Candidate) -> dict:
        diff = self.diffs.get(rel)
        if diff is None:
            return {"status": "unchanged", "added": [], "removed": []}
        candidates = self.candidates(rel)
        added = [n for n in diff.added if candidate.start <= n <= candidate.end]
        removed = []
        for block in diff.removed:
            owner = self.block_owner(rel, candidates, block, set(diff.added))
            if owner and candidate.start <= owner.start and owner.end <= candidate.end:
                removed.append({"after": block.after, "text": block.lines})
        status = "unchanged"
        if candidate.id in self.changed_set:
            whole = all(n in set(added) for n in range(candidate.start, candidate.end + 1))
            status = "added" if whole else "modified"
        return {"status": status, "added": added, "removed": removed}

    def add_node(self, candidate: Candidate, depth: int, up: int, direction: str) -> bool:
        if candidate.id in self.nodes:
            return False
        if len(self.nodes) >= self.caps.max_nodes:
            self.max_nodes_hit = True
            return False
        rel = self.path_by_id[candidate.id]
        language = self.language(rel)
        self.nodes[candidate.id] = {
            "id": candidate.id, "name": candidate.name, "qualname": candidate.qualname, "kind": candidate.kind,
            "path": rel, "language": language.name if language else None,
            "lines": [candidate.start, candidate.end],
            "source": "\n".join(self.lines(rel)[candidate.start - 1:candidate.end]),
            "change": self.change_for(rel, candidate), "links": [], "external": [], "callers": [],
            "callersComputed": False, "implementations": [], "depth": depth, "up": up,
            "direction": direction, "test": self.config.is_test(rel)}
        return True

    def file_tokens(self, rel: str) -> list:
        if rel not in self.tokens_cache:
            def fetch(server, path):
                data = server.semantic_tokens(path)
                return decode_semantic_tokens(data, server.token_types) if data else None
            try:
                tokens = self.call(rel, fetch)
            except RootLost:
                tokens = []
            if tokens is None:
                lines = self.lines(rel)
                tokens = regex_tokens(lines, self.language(rel).identifier_pattern, 0, len(lines) - 1)
            self.tokens_cache[rel] = tokens
        return self.tokens_cache[rel]

    def compute_links(self, node_id: str) -> List[Candidate]:
        node = self.nodes[node_id]
        candidate = self.known[node_id]
        rel = node["path"]
        targets: List[Candidate] = []
        if self.key(rel) is None:
            return targets
        tokens = [t for t in linkable(self.file_tokens(rel))
                  if candidate.start - 1 <= t.line <= candidate.end - 1
                  and not (t.line == candidate.sel_line and t.col == candidate.sel_char)]
        try:
            answers = self.call(rel, lambda server, path: server.definitions(path, [(t.line, t.col) for t in tokens]))
        except RootLost:
            return targets
        for token, locations in zip(tokens, answers):
            if not locations:
                continue
            location = locations[0]
            span = {"line": token.line + 1, "col": token.col, "len": token.length}
            target_rel = self.relative(uri_to_path(location.uri))
            if target_rel is None:
                node["external"].append({**span, "package": external_package(location.uri)})
                continue
            if target_rel == rel and candidate.start - 1 <= location.line0 <= candidate.end - 1:
                continue
            target = self.node_at(target_rel, location.line0 + 1)
            if target is None:
                node["links"].append({**span, "path": target_rel, "targetLine": location.line0 + 1})
                continue
            node["links"].append({**span, "to": target.id})
            targets.append(target)
        return targets

    def compute_callers(self, node_id: str) -> List[Candidate]:
        node = self.nodes[node_id]
        candidate = self.known[node_id]
        rel = node["path"]
        node["callersComputed"] = True
        if candidate.kind == "toplevel" or self.key(rel) is None:
            return []
        self.open_mentions(rel, candidate.name)
        entries: Dict[str, dict] = {}
        found: List[Candidate] = []

        def record(caller_rel: str, line: int, explicit: bool):
            caller = self.node_at(caller_rel, line) or self.toplevel_at(caller_rel, line)
            if caller.id == node_id:
                return
            if caller.id not in entries:
                entries[caller.id] = {"from": caller.id, "path": caller_rel, "line": caller.start, "lines": [],
                                      "test": self.config.is_test(caller_rel)}
                found.append(caller)
            if explicit and line not in entries[caller.id]["lines"]:
                entries[caller.id]["lines"].append(line)

        try:
            items = self.call(rel, lambda s, p: s.prepare_call_hierarchy(p, candidate.sel_line, candidate.sel_char))
            if items:
                for call in self.call(rel, lambda s, p: s.incoming_calls(items[0])):
                    caller_rel = self.relative(uri_to_path(call["from"]["uri"]))
                    if caller_rel is None:
                        continue
                    ranges = call.get("fromRanges") or []
                    for r in ranges:
                        record(caller_rel, r["start"]["line"] + 1, True)
                    if not ranges:
                        record(caller_rel, call["from"]["selectionRange"]["start"]["line"] + 1, False)
            else:
                for location in self.call(rel, lambda s, p: s.references(p, candidate.sel_line, candidate.sel_char)):
                    caller_rel = self.relative(uri_to_path(location.uri))
                    if caller_rel is not None:
                        record(caller_rel, location.line0 + 1, True)
        except RootLost:
            node["callersComputed"] = False
            return []
        node["callers"] = sorted(entries.values(), key=lambda e: e["from"])
        return found

    def open_mentions(self, rel: str, name: str) -> None:
        key = self.key(rel)
        if key is None or not name:
            return
        language = self.config.languages[key[0]]
        if not language.open_mentions:
            return
        scope = key[1].relative_to(self.root).as_posix() or "."
        found = gitops.run_git(self.root, "grep", "-l", "-w", "-F", "--untracked", "-e", name, "--", scope, check=False)
        for path in found.splitlines()[:200]:
            if Path(path).suffix in language.extensions and path != rel:
                try:
                    self.call(path, lambda server, absolute: None)
                except RootLost:
                    return

    def wants_implementations(self, candidate: Candidate, rel: str) -> bool:
        if candidate.kind_number == 11:
            return True
        if candidate.parent and any(c.qualname == candidate.parent and c.kind_number == 11 for c in self.candidates(rel)):
            return True
        language = self.language(rel)
        if language and language.implementation_pattern and candidate.kind != "toplevel":
            return re.search(language.implementation_pattern, self.lines(rel)[candidate.start - 1]) is not None
        return False

    def compute_implementations(self, node_id: str) -> List[Candidate]:
        node = self.nodes[node_id]
        candidate = self.known[node_id]
        rel = node["path"]
        if self.key(rel) is None or not self.wants_implementations(candidate, rel):
            return []
        try:
            locations = self.call(rel, lambda s, p: s.implementation(p, candidate.sel_line, candidate.sel_char))
        except RootLost:
            return []
        found = []
        for location in locations:
            target_rel = self.relative(uri_to_path(location.uri))
            target = self.node_at(target_rel, location.line0 + 1) if target_rel else None
            if target is not None and target.id != node_id and target.id not in node["implementations"]:
                node["implementations"].append(target.id)
                found.append(target)
        return found

    def expand(self, changed: List[str]) -> None:
        queue = deque()
        for node_id in changed:
            if self.add_node(self.known[node_id], 0, 0, "seed"):
                queue.append(node_id)
        while queue:
            node_id = queue.popleft()
            node = self.nodes[node_id]
            depth, up, direction = node["depth"], node["up"], node["direction"]
            descends = up == 0 and not node["test"] and node["kind"] in EXPANDING_KINDS
            for target in self.compute_links(node_id) + self.compute_implementations(node_id):
                if descends and depth + 1 <= self.caps.max_down and self.add_node(target, depth + 1, up, "down"):
                    queue.append(target.id)
            if direction in ("seed", "up") or depth <= 1:
                for caller in self.compute_callers(node_id):
                    climbing = direction in ("seed", "up") and up + 1 <= self.caps.max_up
                    if climbing and self.add_node(caller, depth, up + 1, "up"):
                        queue.append(caller.id)

    def finalize(self) -> None:
        for node_id, node in self.nodes.items():
            for link in node["links"]:
                if "to" in link and link["to"] not in self.nodes:
                    target = self.known[link.pop("to")]
                    link["path"] = self.path_by_id[target.id]
                    link["targetLine"] = target.start
            node["implementations"] = [i for i in node["implementations"] if i in self.nodes]
            for entry in node["callers"]:
                if not entry["lines"] and entry["from"] in self.nodes:
                    entry["lines"] = sorted({l["line"] for l in self.nodes[entry["from"]]["links"] if l.get("to") == node_id})

    def untracked_diff(self, rel: str) -> FileDiff:
        try:
            text = (self.root / rel).read_text()
        except (UnicodeDecodeError, OSError):
            return FileDiff(path=rel, status="binary")
        return FileDiff(path=rel, status="added", added=list(range(1, len(split_lines(text)) + 1)))

    def build(self, meta: dict) -> dict:
        started = time.time()
        diffs = parse_diff(gitops.diff_text(self.root, self.base_sha))
        diffs += [self.untracked_diff(rel) for rel in gitops.untracked_files(self.root)]
        for diff in diffs:
            self.diffs[diff.path] = diff
            language = self.config.language_for(diff.path)
            self.files[diff.path] = {"language": language.name if language else None, "status": diff.status,
                                     "added": len(diff.added), "removed": diff.removed_count,
                                     "generated": self.config.is_generated(diff.path), "oldPath": diff.old_path}
        changed, hunks = self.find_changes()
        self.changed_set = set(changed)
        self.expand(changed)
        self.finalize()
        upward = {i for i, n in self.nodes.items() if n["direction"] in ("seed", "up")}
        entries, test_entries = entry_points(self.nodes, upward)
        impact = impact_paths(changed, self.nodes, set(entries), self.caps.impact_paths)
        head = gitops.run_git(self.root, "rev-parse", "HEAD").strip()
        dirty = bool(gitops.run_git(self.root, "status", "--porcelain").strip())
        return {
            "meta": {**meta, "base": self.base_sha, "head": head, "dirty": dirty,
                     "languages": sorted({n["language"] for n in self.nodes.values() if n["language"]}),
                     "seconds": round(time.time() - started, 1)},
            "files": self.files, "nodes": self.nodes, "hunks": hunks, "changed": changed,
            "entryPoints": entries, "testEntryPoints": test_entries, "impact": impact,
            "parts": parts(changed, self.nodes), "signals": signals(changed, self.nodes, impact),
            "lostLinks": [{"root": k[1].relative_to(self.root).as_posix() or ".", "language": k[0], "reason": v}
                          for k, v in self.lost.items()],
            "truncated": {"maxNodesHit": self.max_nodes_hit},
        }

    def close(self) -> None:
        for server in self.servers.values():
            server.stop()


def build_index(root: Path, base_sha: str, config: Config, caps: Optional[Caps] = None,
                skip_languages=(), meta: Optional[dict] = None, log=None) -> dict:
    indexer = Indexer(root, base_sha, config, caps or Caps(), skip_languages, log)
    try:
        return indexer.build(meta or {})
    finally:
        indexer.close()
