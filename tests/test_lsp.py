import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from walkthrough.config import load_config
from walkthrough.lsp import LspServer, uri_to_path

CORE = "def helper(x):\n    return x + 1\n\n\ndef main():\n    return helper(1)\n"
OTHER = "from pkg.core import helper\n\n\ndef use():\n    return helper(2)\n"


class LspTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        language = load_config().languages["python"]
        if not language.installed():
            raise AssertionError(f"basedpyright is missing. Install with: {language.install}")
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name).resolve()
        (root / "pyproject.toml").write_text('[project]\nname = "probe"\nversion = "0"\n')
        (root / "pkg").mkdir()
        (root / "pkg" / "__init__.py").write_text("")
        cls.core = root / "pkg" / "core.py"
        cls.other = root / "pkg" / "other.py"
        cls.core.write_text(CORE)
        cls.other.write_text(OTHER)
        cls.server = LspServer(list(language.command), root)
        cls.server.start()
        cls.server.open(cls.core, "python")
        cls.server.open(cls.other, "python")

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.tmp.cleanup()

    def test_document_symbols_list_the_functions(self):
        names = [s["name"] for s in self.server.document_symbols(self.core)]
        self.assertEqual(names[:2], ["helper", "main"])

    def test_definition_follows_an_import_to_the_other_file(self):
        locations = self.server.definition(self.other, 4, 11)
        self.assertEqual(uri_to_path(locations[0].uri), self.core)
        self.assertEqual(locations[0].line0, 0)

    def test_batched_definitions_match_single_requests(self):
        positions = [(4, 11), (4, 4), (0, 5)]
        batch = self.server.definitions(self.other, positions)
        single = [self.server.definition(self.other, line, char) for line, char in positions]
        self.assertEqual(batch, single)
        self.assertEqual(uri_to_path(batch[0][0].uri), self.core)

    def test_incoming_calls_find_callers_in_both_files(self):
        items = self.server.prepare_call_hierarchy(self.core, 0, 4)
        callers = {call["from"]["name"] for call in self.server.incoming_calls(items[0])}
        self.assertEqual(callers, {"main", "use"})

    def test_semantic_tokens_are_available(self):
        self.assertTrue(self.server.supports("semanticTokensProvider"))
        self.assertTrue(self.server.semantic_tokens(self.core))
        self.assertIn("function", self.server.token_types)

    def test_references_work_as_the_callers_fallback(self):
        paths = {uri_to_path(loc.uri) for loc in self.server.references(self.core, 0, 4)}
        self.assertEqual(paths, {self.core, self.other})


if __name__ == "__main__":
    unittest.main()
