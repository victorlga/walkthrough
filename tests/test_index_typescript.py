import tempfile
import unittest

from helpers import base_sha, make_fixture_repo
from walkthrough.config import load_config
from walkthrough.indexer import build_index

P = "src/pricing.ts#"


class TypeScriptIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()
        if not config.languages["typescript"].installed():
            raise AssertionError(f"typescript-language-server is missing. Install with: {config.languages['typescript'].install}")
        cls.tmp = tempfile.TemporaryDirectory()
        repo = make_fixture_repo("typescript", cls.tmp.name)
        cls.index = build_index(repo, base_sha(repo), config)
        cls.nodes = cls.index["nodes"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_changed_functions(self):
        self.assertEqual(self.index["changed"], ["src/api.ts#handler", P + "discount", P + "basePrice"])
        self.assertEqual(self.nodes[P + "discount"]["change"]["status"], "added")

    def test_links_skip_the_local_constant(self):
        self.assertEqual(sorted({l.get("to") for l in self.nodes[P + "basePrice"]["links"]}), [P + "RATE", P + "discount"])

    def test_standard_library_is_external(self):
        self.assertTrue(any(e["package"] == "typescript" for e in self.nodes[P + "describe"]["external"]))

    def test_a_test_inside_an_anonymous_callback_is_still_a_test_caller(self):
        callers = self.nodes[P + "basePrice"]["callers"]
        self.assertTrue(any(c["path"] == "test/pricing.spec.ts" and c["test"] for c in callers))
        self.assertTrue(any(i.startswith("test/pricing.spec.ts") for i in self.index["testEntryPoints"]))

    def test_interface_methods_list_their_implementations(self):
        self.assertEqual(self.nodes["src/store.ts#PriceStore.save"]["implementations"], ["src/store.ts#MemoryStore.save"])

    def test_impact_reaches_the_handler(self):
        self.assertEqual(self.index["impact"][P + "basePrice"]["paths"][0], [P + "basePrice", P + "describe", "src/api.ts#handler"])


if __name__ == "__main__":
    unittest.main()
