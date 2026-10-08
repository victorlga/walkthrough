import tempfile
import unittest
from pathlib import Path

from helpers import git, init_repo
from walkthrough.config import load_config
from walkthrough.indexer import build_index

BASE = """def alpha():
    a = 1
    b = 2
    return a


def beta():
    return 2


def gamma():
    return 3


def delta():
    x = 1
    return x
"""

HEAD = """def alpha():
    a = 1
    return a


def gamma():
    return 3


def delta():
    x = 1
"""


class RemovedCodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()
        cls.tmp = tempfile.TemporaryDirectory()
        repo = init_repo(Path(cls.tmp.name) / "repo")
        (repo / "mod.py").write_text(BASE)
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "base")
        base = git(repo, "rev-parse", "HEAD").strip()
        git(repo, "checkout", "-b", "feature")
        (repo / "mod.py").write_text(HEAD)
        git(repo, "commit", "-am", "drop beta")
        cls.index = build_index(repo.resolve(), base, config)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_deleted_function_is_a_removed_hunk_not_a_change_to_its_neighbor(self):
        self.assertNotIn("mod.py#gamma", self.index["changed"])
        removed = [line["text"] for hunk in self.index["hunks"] for line in hunk["lines"] if line["kind"] == "del"]
        self.assertIn("def beta():", removed)

    def test_lines_removed_inside_a_function_still_belong_to_it(self):
        self.assertEqual(self.index["changed"], ["mod.py#alpha", "mod.py#delta"])


if __name__ == "__main__":
    unittest.main()
