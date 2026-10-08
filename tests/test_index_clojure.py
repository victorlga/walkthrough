import tempfile
import unittest

from helpers import base_sha, make_fixture_repo
from walkthrough.config import load_config
from walkthrough.indexer import build_index

P = "src/shop/pricing.clj#"


class ClojureIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()
        if not config.languages["clojure"].installed():
            raise AssertionError(f"clojure-lsp is missing. Install with: {config.languages['clojure'].install}")
        cls.tmp = tempfile.TemporaryDirectory()
        repo = make_fixture_repo("clojure", cls.tmp.name)
        cls.index = build_index(repo, base_sha(repo), config)
        cls.nodes = cls.index["nodes"]
        pricing = [n for n in cls.nodes.values() if n["path"] == "src/shop/pricing.clj"]
        cls.defmulti = next(n for n in pricing if n["source"].startswith("(defmulti"))
        cls.defmethods = sorted(n["id"] for n in pricing if n["source"].startswith("(defmethod"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_names_with_arrows_keep_their_ids(self):
        self.assertEqual(self.nodes[P + "amount->cents"]["change"]["status"], "added")
        self.assertIn(P + "amount->cents", self.index["changed"])

    def test_links_go_to_the_multimethod_and_the_var_but_not_the_let_binding(self):
        targets = {l.get("to") for l in self.nodes[P + "base-price"]["links"]}
        self.assertEqual(targets, {self.defmulti["id"], P + "rate"})
        self.assertTrue(any(e["package"].startswith("clojure") for e in self.nodes[P + "base-price"]["external"]))

    def test_multimethod_lists_its_defmethods(self):
        self.assertEqual(len(self.defmethods), 2)
        self.assertEqual(sorted(self.defmulti["implementations"]), self.defmethods)

    def test_callers_get_call_lines_even_without_call_site_ranges(self):
        callers = {c["from"]: c for c in self.nodes[P + "base-price"]["callers"]}
        self.assertEqual(set(callers), {P + "describe", "test/shop/pricing_test.clj#base-price-test"})
        self.assertTrue(callers["test/shop/pricing_test.clj#base-price-test"]["test"])
        self.assertTrue(callers[P + "describe"]["lines"])

    def test_entry_points(self):
        self.assertEqual(self.index["entryPoints"], ["src/shop/api.clj#handler"])
        self.assertEqual(self.index["testEntryPoints"], ["test/shop/pricing_test.clj#base-price-test"])


if __name__ == "__main__":
    unittest.main()
