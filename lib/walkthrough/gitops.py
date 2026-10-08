from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set


class GitError(Exception):
    pass


def run_git(root: Path, *args, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def repo_root(path: Path) -> Path:
    return Path(run_git(path, "rev-parse", "--show-toplevel").strip()).resolve()


def repo_name(root: Path) -> str:
    common = run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    return Path(common).resolve().parent.name


def default_base(root: Path) -> str:
    ref = run_git(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False).strip()
    if not ref:
        raise GitError("Could not find the main branch from origin/HEAD. Pass --base <ref>.")
    return ref.replace("refs/remotes/", "", 1)


def merge_base(root: Path, base_ref: str, head: str = "HEAD") -> str:
    found = run_git(root, "merge-base", base_ref, head, check=False).strip()
    if not found:
        raise GitError(f"{head} has no common history with {base_ref}. Pass --base <ref> with a commit both share.")
    return found


def diff_text(root: Path, base_sha: str) -> str:
    return run_git(root, "diff", "--no-color", "--no-ext-diff", "-U0", "-M", base_sha)


def untracked_files(root: Path) -> List[str]:
    return [line for line in run_git(root, "ls-files", "--others", "--exclude-standard").splitlines() if line]


def repo_files(root: Path) -> Set[str]:
    tracked = {line for line in run_git(root, "ls-files").splitlines() if line}
    return tracked | set(untracked_files(root))


def commit_subjects(root: Path, base_sha: str) -> List[str]:
    return [line for line in run_git(root, "log", "--format=%s", f"{base_sha}..HEAD").splitlines() if line]


def current_branch(root: Path) -> Optional[str]:
    name = run_git(root, "branch", "--show-current", check=False).strip()
    return name or None


def slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "head"


@dataclass
class Target:
    root: Path
    base_sha: str
    label: str
    title: str
    body: str
    slug: str
    worktree: Optional[Path]
    pr: Optional[int]


def gh_json(repo: Path, *args) -> Optional[dict]:
    if shutil.which("gh") is None:
        return None
    result = subprocess.run(["gh", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def add_worktree(repo: Path, run_dir: Path, sha: str) -> Path:
    worktree = (run_dir / "worktree").resolve()
    if worktree.exists():
        remove_worktree(repo, worktree)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_git(repo, "worktree", "add", "--detach", str(worktree), sha)
    return worktree


def remove_worktree(repo: Path, worktree: Path) -> None:
    if worktree.exists():
        run_git(repo, "worktree", "remove", "--force", str(worktree), check=False)
    if worktree.exists():
        shutil.rmtree(worktree)
    run_git(repo, "worktree", "prune", check=False)


def resolve_target(repo: Path, target: Optional[str], base: Optional[str], run_dir: Path) -> Target:
    repo = repo_root(repo)
    branch = current_branch(repo)
    if target is None or target == branch:
        base_sha = merge_base(repo, base or default_base(repo))
        pr = gh_json(repo, "pr", "view", "--json", "number,title,body")
        title = pr["title"] if pr else (branch or "HEAD")
        return Target(root=repo, base_sha=base_sha, label=branch or "HEAD", title=title,
                      body=pr["body"] if pr else "", slug=slugify(branch or "HEAD"),
                      worktree=None, pr=pr["number"] if pr else None)
    if target.isdigit():
        number = int(target)
        pr = gh_json(repo, "pr", "view", target, "--json", "headRefOid,baseRefName,title,body")
        if pr is None:
            raise GitError(f"gh could not read PR {number}. Check `gh auth status` and the PR number.")
        run_git(repo, "fetch", "origin", f"pull/{number}/head", pr["baseRefName"])
        base_sha = merge_base(repo, base or f"origin/{pr['baseRefName']}", pr["headRefOid"])
        worktree = add_worktree(repo, run_dir, pr["headRefOid"])
        return Target(root=worktree, base_sha=base_sha, label=f"PR {number}", title=pr["title"],
                      body=pr["body"] or "", slug=f"pr-{number}", worktree=worktree, pr=number)
    sha = run_git(repo, "rev-parse", "--verify", f"{target}^{{commit}}", check=False).strip()
    if not sha:
        sha = run_git(repo, "rev-parse", "--verify", f"origin/{target}^{{commit}}", check=False).strip()
    if not sha:
        raise GitError(f"Branch {target} does not exist locally or on origin.")
    base_sha = merge_base(repo, base or default_base(repo), sha)
    worktree = add_worktree(repo, run_dir, sha)
    return Target(root=worktree, base_sha=base_sha, label=target, title=target, body="",
                  slug=slugify(target), worktree=worktree, pr=None)
