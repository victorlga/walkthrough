import tempfile
import unittest
from pathlib import Path

from helpers import git, init_repo
from walkthrough.config import load_config
from walkthrough.indexer import block_around, build_index, merge_adjacent_links
from walkthrough.symbols import Candidate, include_leading_comments


def candidate(name, start, end):
    return Candidate(name=name, qualname=name, kind="function", kind_number=12, start=start, end=end,
                     sel_line=start - 1, sel_char=0, depth=0, parent=None, id=name)


class LeadingCommentsTest(unittest.TestCase):
    def test_a_doc_comment_right_above_a_function_belongs_to_it(self):
        lines = ["const a = 1;", "", "/**", " * Adds one.", " */", "function inc(x) {", "  return x + 1;", "}"]
        found = [candidate("a", 1, 1), candidate("inc", 6, 8)]
        include_leading_comments(found, lines, ("//", "/*", "*"))
        self.assertEqual([c.start for c in found], [1, 3])

    def test_a_comment_inside_the_previous_function_stays_there(self):
        lines = ["(defn a []", "  1", "  ;; tail of a", ")", ";; about b", "(defn b [] 2)"]
        found = [candidate("a", 1, 4), candidate("b", 6, 6)]
        include_leading_comments(found, lines, (";",))
        self.assertEqual([c.start for c in found], [1, 5])


class MergeLinksTest(unittest.TestCase):
    def test_a_qualified_name_split_in_tokens_becomes_one_link(self):
        links = [{"line": 31, "col": 40, "len": 8, "to": "e.clj#Tier"}, {"line": 31, "col": 48, "len": 1, "to": "e.clj#Tier"},
                 {"line": 31, "col": 49, "len": 4, "to": "e.clj#Tier"}, {"line": 31, "col": 55, "len": 3, "to": "e.clj#Tier"},
                 {"line": 32, "col": 0, "len": 3, "path": "x.clj", "targetLine": 4}]
        self.assertEqual(merge_adjacent_links(links), [
            {"line": 31, "col": 40, "len": 13, "to": "e.clj#Tier"}, {"line": 31, "col": 55, "len": 3, "to": "e.clj#Tier"},
            {"line": 32, "col": 0, "len": 3, "path": "x.clj", "targetLine": 4}])


class BlockAroundTest(unittest.TestCase):
    def test_an_import_change_shows_the_whole_import_block(self):
        lines = ["import a", "import b", "import c", "", "def f():", "    pass"]
        self.assertEqual(block_around(lines, 2, 2), (1, 3))

    def test_a_namespace_docstring_change_shows_the_whole_form(self):
        lines = ["(ns app.core", "  \"Prices orders.", "", "   Never falls back.\"", "  (:require [x]))", "", "(defn g [] 1)"]
        self.assertEqual(block_around(lines, 4, 4), (1, 5))

    def test_a_huge_block_is_cut_around_the_change(self):
        lines = [f"KEY_{n}=value" for n in range(1, 201)]
        self.assertEqual(block_around(lines, 100, 100), (80, 120))


BASE = """import os
import sys


# Adds one.
def inc(x):
    return x + 1
"""

HEAD = """import os
import re
import sys


# Adds one to x.
def inc(x):
    return x + 1
"""


class ContextIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        repo = init_repo(Path(cls.tmp.name) / "repo")
        (repo / "mod.py").write_text(BASE)
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "base")
        base = git(repo, "rev-parse", "HEAD").strip()
        (repo / "mod.py").write_text(HEAD)
        cls.index = build_index(repo.resolve(), base, load_config())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_editing_a_doc_comment_changes_the_function_it_documents(self):
        self.assertEqual(self.index["changed"], ["mod.py#inc"])
        self.assertEqual(self.index["nodes"]["mod.py#inc"]["lines"][0], 6)

    def test_an_import_hunk_shows_its_whole_block(self):
        [hunk] = self.index["hunks"]
        self.assertEqual([line["text"] for line in hunk["lines"]], ["import os", "import re", "import sys"])


if __name__ == "__main__":
    unittest.main()


SCHEMA_BASE = """LIMIT = 10


def deep():
    return 2


def helper():
    return deep()


RULES = {"limit": LIMIT}
"""

SCHEMA_HEAD = """LIMIT = 10


def deep():
    return 2


def helper():
    return deep()


RULES = {"limit": LIMIT, "helper": helper}
"""


class ChangedConstantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        repo = init_repo(Path(cls.tmp.name) / "repo")
        (repo / "rules.py").write_text(SCHEMA_BASE)
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "base")
        base = git(repo, "rev-parse", "HEAD").strip()
        (repo / "rules.py").write_text(SCHEMA_HEAD)
        cls.index = build_index(repo.resolve(), base, load_config())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_changed_constant_opens_what_it_uses_one_level_deep(self):
        self.assertEqual(self.index["changed"], ["rules.py#RULES"])
        self.assertIn("rules.py#LIMIT", self.index["nodes"])
        self.assertIn("rules.py#helper", self.index["nodes"])
        self.assertNotIn("rules.py#deep", self.index["nodes"])

    def test_an_edited_one_line_definition_is_modified_not_added(self):
        self.assertEqual(self.index["nodes"]["rules.py#RULES"]["change"]["status"], "modified")
