from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

from walkthrough import explanations as explanations_store
from walkthrough import gitops
from walkthrough.config import load_config
from walkthrough.indexer import Caps, build_index
from walkthrough.render import render
from walkthrough.validate import prune, validate

GLOSSARY_NAMES = ("CONTEXT.md", "GLOSSARY.md")


def cache_root() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "walkthrough"


def target_slug(repo: Path, target) -> str:
    if target is None:
        return gitops.slugify(gitops.current_branch(repo) or "HEAD")
    return f"pr-{target}" if target.isdigit() else gitops.slugify(target)


def changed_paths(root: Path, base_sha: str) -> List[str]:
    names = set(gitops.names(root, "diff", "--name-only", base_sha))
    return sorted(names | set(gitops.untracked_files(root)))


def paths_for_target(repo: Path, target, base) -> List[str]:
    if target is None or target == gitops.current_branch(repo):
        return changed_paths(repo, gitops.merge_base(repo, base or gitops.default_base(repo)))
    if target.isdigit():
        result = subprocess.run(["gh", "pr", "diff", target, "--name-only"], cwd=repo, capture_output=True, text=True)
        return [line for line in result.stdout.splitlines() if line]
    sha = gitops.run_git(repo, "rev-parse", "--verify", f"{target}^{{commit}}").strip()
    merge = gitops.merge_base(repo, base or gitops.default_base(repo), sha)
    return gitops.names(repo, "diff", "--name-only", merge, sha)


def find_glossaries(root: Path, paths: List[str]) -> List[str]:
    found = {name for name in GLOSSARY_NAMES if (root / name).is_file()}
    for rel in paths:
        directory = (root / rel).parent
        while directory != root and root in directory.parents:
            for name in GLOSSARY_NAMES:
                if (directory / name).is_file():
                    found.add((directory / name).relative_to(root).as_posix())
            directory = directory.parent
    return sorted(found)


def short_list(items: List[str], limit: int = 15) -> str:
    if not items:
        return "none"
    extra = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return ", ".join(items[:limit]) + extra


def load_run(run_dir: Path):
    index = json.loads((run_dir / "index.json").read_text())
    context_path = run_dir / "context.json"
    context = json.loads(context_path.read_text()) if context_path.exists() else {}
    return index, context


def numbered(node: dict) -> str:
    start = node["lines"][0]
    added = set(node["change"]["added"])
    removed = {}
    for block in node["change"]["removed"]:
        removed.setdefault(block["after"], []).extend(block["text"])
    out = [f"       - {t}" for t in removed.get(start - 1, [])]
    for offset, text in enumerate(node["source"].split("\n")):
        n = start + offset
        out.append(f"{n:4d} {'+' if n in added else ' '} {text}")
        out.extend(f"       - {t}" for t in removed.get(n, []))
    return "\n".join(out)


def cmd_index(args) -> int:
    config = load_config()
    try:
        repo = gitops.repo_root(Path(args.repo or "."))
        run_dir = Path(args.run_dir) if args.run_dir else cache_root() / gitops.repo_name(repo) / target_slug(repo, args.target)
        run_dir.mkdir(parents=True, exist_ok=True)
        target = gitops.resolve_target(repo, args.target, args.base, run_dir)
    except gitops.GitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    code = 1
    try:
        code = index_target(args, config, repo, run_dir, target)
    finally:
        if code != 0 and target.worktree:
            gitops.remove_worktree(repo, target.worktree)
    return code


def clear_previous_run(run_dir: Path) -> None:
    for name in ("explanations.json", "plan.json"):
        (run_dir / name).unlink(missing_ok=True)
    shutil.rmtree(run_dir / "fragments", ignore_errors=True)


def index_target(args, config, repo: Path, run_dir: Path, target) -> int:
    paths = changed_paths(target.root, target.base_sha)
    if not paths:
        print("error: there are no changes between this branch and its base", file=sys.stderr)
        return 1
    skip = set(args.skip_language)
    needed = sorted({config.language_for(p).name for p in paths if config.language_for(p)} - skip)
    missing = [config.languages[name] for name in needed if not config.languages[name].installed()]
    if missing:
        for language in missing:
            print(f"error: the diff has {language.name} files and {language.command[0]} is not installed. "
                  f"Install with: {language.install}", file=sys.stderr)
        print("Re-run with --skip-language <name> to index those files without links.", file=sys.stderr)
        return 2
    meta = {"repo": gitops.repo_name(repo), "repoPath": str(repo), "label": target.label, "title": target.title,
            "pr": target.pr, "slug": target.slug, "root": str(target.root),
            "worktree": str(target.worktree) if target.worktree else None}
    caps = Caps(max_nodes=args.max_nodes, max_down=args.max_down, max_up=args.max_up)
    index = build_index(target.root, target.base_sha, config, caps, tuple(skip), meta,
                        log=lambda message: print(message, file=sys.stderr))
    clear_previous_run(run_dir)
    (run_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False))
    context = {"body": target.body, "commits": gitops.commit_subjects(target.root, target.base_sha),
               "glossary": find_glossaries(target.root, paths)}
    (run_dir / "context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2))
    print(run_dir)
    print(f"{len(index['changed'])} changed functions, {len(index['nodes'])} indexed, "
          f"{len(index['hunks'])} hunks, {index['meta']['seconds']}s")
    return 0


def cmd_summary(args) -> int:
    index, context = load_run(Path(args.run_dir))
    meta = index["meta"]
    print(f"# {meta.get('title')} ({meta.get('label')}) base {meta['base'][:8]} head {meta['head'][:8]}"
          + (" dirty" if meta.get("dirty") else ""))
    print("files:")
    for path, info in sorted(index["files"].items()):
        flag = " generated" if info["generated"] else ""
        print(f"  {info['status']:<8} {path} +{info['added']} -{info['removed']} {info['language'] or '-'}{flag}")
    print("changed functions (id | status | lines changed | linked changes | reaches entry | test):")
    for node_id in index["changed"]:
        node, signal = index["nodes"][node_id], index["signals"][node_id]
        print(f"  {node_id} | {node['change']['status']} | {signal['linesChanged']} | {signal['linkedChanges']} | "
              f"{'yes' if signal['onEntryPath'] else 'no'} | {'yes' if node['test'] else 'no'}")
    print("suggested parts:")
    for number, part in enumerate(index["parts"], 1):
        print(f"  {number}: {', '.join(part)}")
    print(f"entry points: {short_list(index['entryPoints'])}")
    print(f"test entry points: {short_list(index['testEntryPoints'])}")
    print(f"hunks: {short_list([h['id'] for h in index['hunks']], 50)}")
    for lost in index["lostLinks"]:
        print(f"lost links: {lost['language']} at {lost['root']}: {lost['reason']}")
    print(f"functions indexed: {len(index['nodes'])}" + (" (hit max nodes)" if index["truncated"]["maxNodesHit"] else ""))
    print("commits:")
    for subject in context.get("commits", []):
        print(f"  - {subject}")
    print(f"glossary: {', '.join(context.get('glossary', [])) or 'none'}")
    if context.get("body"):
        print("pr description:")
        print("\n".join(context["body"].splitlines()[:60]))
    return 0


def cmd_context(args) -> int:
    run_dir = Path(args.run_dir)
    index, context = load_run(run_dir)
    node = index["nodes"].get(args.id)
    hunk = next((h for h in index.get("hunks", []) if h["id"] == args.id), None)
    if node is None and hunk is not None:
        marks = {"add": "+", "del": "-", "ctx": " "}
        print(f"# {hunk['id']} (hunk outside any function) {hunk['path']}")
        for line in hunk["lines"]:
            print(f"{str(line['n']).rjust(4) if line['n'] else '    '} {marks[line['kind']]} {line['text']}")
        return 0
    if node is None:
        print(f"error: {args.id} is not in the index", file=sys.stderr)
        return 1
    nodes = index["nodes"]
    print(f"# {node['id']} ({node['kind']}, {node['change']['status']}) {node['path']}:{node['lines'][0]}-{node['lines'][1]}")
    print(numbered(node))
    print("links:")
    for link in node["links"]:
        print(f"  line {link['line']}: {link.get('to') or link['path'] + ':' + str(link['targetLine'])}")
    print("callers:")
    for caller in node["callers"]:
        print(f"  {caller['from']}{' (test)' if caller['test'] else ''} lines {caller['lines']}")
    if node["implementations"]:
        print(f"implementations: {', '.join(node['implementations'])}")
    impact = index["impact"].get(node["id"])
    if impact:
        for path in impact["paths"]:
            print(f"impact: {' <- '.join(reversed(path))}")
    neighbors = [l["to"] for l in node["links"] if "to" in l] + [c["from"] for c in node["callers"]]
    for neighbor in dict.fromkeys(neighbors):
        if neighbor in nodes:
            source = numbered(nodes[neighbor]).split("\n")
            print(f"\n## neighbor {neighbor}")
            print("\n".join(source[:80]) + ("\n  ..." if len(source) > 80 else ""))
    print(f"\nglossary: {', '.join(context.get('glossary', [])) or 'none'}")
    explanations = run_dir / "explanations.json"
    if explanations.exists():
        story = json.loads(explanations.read_text()).get("overview", {}).get("story")
        if story:
            print("\n## story of the branch\n" + story)
    return 0


def cmd_doctor(args) -> int:
    config = load_config()
    problems = 0
    if sys.version_info < (3, 9):
        print("python3 3.9 or newer is required")
        problems += 1
    if args.target and args.target.isdigit() and shutil.which("gh") is None:
        print("gh is missing: brew install gh")
        problems += 1
    if args.languages:
        names = args.languages.split(",")
    else:
        try:
            repo = gitops.repo_root(Path(args.repo or "."))
            paths = paths_for_target(repo, args.target, args.base)
            names = sorted({config.language_for(p).name for p in paths if config.language_for(p)})
            print(f"languages in the diff: {', '.join(names) or 'none'}")
        except gitops.GitError as error:
            print(f"could not read the diff ({error}); checking every language")
            names = list(config.languages)
    for name in names:
        language = config.languages[name]
        ok = language.installed()
        print(f"{name}\t{'ok' if ok else 'missing'}\t{' '.join(language.command)}")
        if not ok:
            print(f"  install: {language.install}")
            problems += 1
    return 1 if problems else 0


def cmd_cleanup(args) -> int:
    worktree = Path(args.run_dir) / "worktree"
    if not worktree.exists():
        print("no worktree to remove")
        return 0
    try:
        common = gitops.run_git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        gitops.remove_worktree(Path(common).parent, worktree.resolve())
    except gitops.GitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"removed {worktree}")
    return 0


def cmd_merge(args) -> int:
    run_dir = Path(args.run_dir)
    data = explanations_store.load(run_dir)
    for fragment_path in args.fragments:
        data = explanations_store.merge(data, json.loads(Path(fragment_path).read_text()))
    explanations_store.save(run_dir, data)
    print(f"{len(data['nodes'])} explanations in {run_dir / 'explanations.json'}")
    return 0


def cmd_validate(args) -> int:
    run_dir = Path(args.run_dir)
    index, _ = load_run(run_dir)
    plan = json.loads((run_dir / "plan.json").read_text())
    data = explanations_store.load(run_dir)
    problems = validate(index, plan, data, args.max_skeleton)
    if args.prune and problems:
        before = len(data["pruned"])
        problems = prune(data, problems)
        explanations_store.save(run_dir, data)
        for entry in data["pruned"][before:]:
            print(f"pruned {entry['id']}: {entry['reason']}")
        problems = validate(index, plan, data, args.max_skeleton)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problems")
    return 1 if problems else 0


def cmd_render(args) -> int:
    run_dir = Path(args.run_dir)
    result = render(run_dir, Path(args.out), args.mode, args.lang)
    index, _ = load_run(run_dir)
    data = explanations_store.load(run_dir)
    print(result["path"])
    print(f"{result['bytes'] / 1_000_000:.1f} MB")
    for lost in index["lostLinks"]:
        print(f"warning: no links for {lost['language']} at {lost['root']}: {lost['reason']}")
    for entry in data["pruned"]:
        print(f"warning: explanation removed for {entry['id']}: {entry['reason']}")
    if result["trimmed"]:
        print(f"warning: {result['trimmed']} distant functions were cut to fit the page")
    if index["truncated"]["maxNodesHit"]:
        print("warning: the index hit --max-nodes; some links show only file and line")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="walkthrough")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="index a branch or PR")
    index.add_argument("target", nargs="?")
    index.add_argument("--repo")
    index.add_argument("--base")
    index.add_argument("--run-dir")
    index.add_argument("--skip-language", action="append", default=[])
    index.add_argument("--max-nodes", type=int, default=Caps.max_nodes)
    index.add_argument("--max-down", type=int, default=Caps.max_down)
    index.add_argument("--max-up", type=int, default=Caps.max_up)
    index.set_defaults(func=cmd_index)

    summary = sub.add_parser("summary", help="compact view of an index")
    summary.add_argument("run_dir")
    summary.set_defaults(func=cmd_summary)

    context = sub.add_parser("context", help="one function and its neighbors")
    context.add_argument("run_dir")
    context.add_argument("id")
    context.set_defaults(func=cmd_context)

    doctor = sub.add_parser("doctor", help="check tools and language servers")
    doctor.add_argument("target", nargs="?")
    doctor.add_argument("--repo")
    doctor.add_argument("--base")
    doctor.add_argument("--languages")
    doctor.set_defaults(func=cmd_doctor)

    cleanup = sub.add_parser("cleanup", help="remove the temporary worktree")
    cleanup.add_argument("run_dir")
    cleanup.set_defaults(func=cmd_cleanup)

    merge_cmd = sub.add_parser("merge", help="merge explanation fragments")
    merge_cmd.add_argument("run_dir")
    merge_cmd.add_argument("fragments", nargs="+")
    merge_cmd.set_defaults(func=cmd_merge)

    validate_cmd = sub.add_parser("validate", help="check plan and explanations against the index")
    validate_cmd.add_argument("run_dir")
    validate_cmd.add_argument("--max-skeleton", type=int, default=12)
    validate_cmd.add_argument("--prune", action="store_true")
    validate_cmd.set_defaults(func=cmd_validate)

    render_cmd = sub.add_parser("render", help="build the page")
    render_cmd.add_argument("run_dir")
    render_cmd.add_argument("--out", required=True)
    render_cmd.add_argument("--mode", choices=["artifact", "local"], default="artifact")
    render_cmd.add_argument("--lang", default="pt")
    render_cmd.set_defaults(func=cmd_render)
    return parser


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
