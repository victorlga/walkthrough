import tempfile
import unittest

from helpers import base_sha, make_fixture_repo
from walkthrough.config import load_config
from walkthrough.indexer import build_index
from walkthrough.tokens import utf16_len

P = "app/pricing.py#"


class PythonIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()
        if not config.languages["python"].installed():
            raise AssertionError(f"basedpyright is missing. Install with: {config.languages['python'].install}")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_fixture_repo("python", cls.tmp.name)
        cls.index = build_index(cls.repo, base_sha(cls.repo), config)
        cls.nodes = cls.index["nodes"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_changed_functions_are_found_in_file_order(self):
        self.assertEqual(self.index["changed"], [P + "discount", P + "base_price"])
        self.assertEqual(self.nodes[P + "discount"]["change"]["status"], "added")
        self.assertEqual(self.nodes[P + "base_price"]["change"]["status"], "modified")

    def test_links_point_to_repo_functions_but_not_to_locals_or_parameters(self):
        links = self.nodes[P + "base_price"]["links"]
        self.assertEqual(sorted({link.get("to") for link in links}), [P + "RATE", P + "discount"])

    def test_link_columns_survive_accents_and_emoji(self):
        node = self.nodes[P + "base_price"]
        line = node["source"].split("\n")[2]
        link = next(l for l in node["links"] if l.get("to") == P + "discount")
        self.assertEqual(link["col"], utf16_len(line[:line.index("discount")]))
        self.assertEqual(link["len"], len("discount"))

    def test_library_calls_are_not_links(self):
        describe = self.nodes[P + "describe"]
        self.assertTrue(any(e["package"] == "stdlib" for e in describe["external"]))
        self.assertFalse(any(l.get("to", "").startswith("json") for l in describe["links"]))

    def test_callers_include_the_test_marked_as_test(self):
        callers = {c["from"]: c["test"] for c in self.nodes[P + "base_price"]["callers"]}
        self.assertEqual(callers, {P + "describe": False, "tests/test_pricing.py#test_base_price": True})

    def test_entry_points_and_impact_reach_the_handler(self):
        self.assertEqual(self.index["entryPoints"], ["app/api.py#handler"])
        self.assertEqual(self.index["testEntryPoints"], ["tests/test_pricing.py#test_base_price"])
        self.assertEqual(self.index["impact"][P + "base_price"]["paths"][0],
                         [P + "base_price", P + "describe", "app/api.py#handler"])

    def test_markdown_change_becomes_a_hunk(self):
        hunk = next(h for h in self.index["hunks"] if h["path"] == "README.md")
        self.assertIn({"n": 3, "kind": "add", "text": "Prices now include a discount."}, hunk["lines"])

    def test_untracked_file_enters_the_index(self):
        extra = self.repo / "app" / "extra.py"
        extra.write_text("def extra():\n    return 1\n")
        try:
            index = build_index(self.repo, base_sha(self.repo), load_config())
        finally:
            extra.unlink()
        self.assertEqual(index["nodes"]["app/extra.py#extra"]["change"]["status"], "added")


class DocsOnlyIndexTest(unittest.TestCase):
    def test_a_branch_without_code_has_hunks_and_no_functions(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_fixture_repo("docs-only", tmp)
            index = build_index(repo, base_sha(repo), load_config())
        self.assertEqual(index["nodes"], {})
        self.assertEqual(index["changed"], [])
        self.assertEqual([h["path"] for h in index["hunks"]], ["README.md"])


if __name__ == "__main__":
    unittest.main()
