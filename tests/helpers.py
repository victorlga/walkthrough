import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
FIXTURES = ROOT / "tests" / "fixtures"
import subprocess


def git(cwd, *args):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


def init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "walkthrough@example.com")
    git(path, "config", "user.name", "Walkthrough Test")
    return path
import shutil


def make_fixture_repo(name, tmp):
    repo = init_repo(Path(tmp) / name)
    shutil.copytree(FIXTURES / name / "base", repo, dirs_exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")
    git(repo, "checkout", "-b", "feature")
    shutil.copytree(FIXTURES / name / "head", repo, dirs_exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "change")
    return repo.resolve()


def base_sha(repo):
    return git(repo, "rev-parse", "main").strip()
