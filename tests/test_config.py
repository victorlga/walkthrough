import unittest

import helpers  # noqa: F401
from walkthrough.config import load_config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_language_comes_from_the_extension(self):
        self.assertEqual(self.config.language_for("app/src/a/core.clj").name, "clojure")
        self.assertEqual(self.config.language_for("src/x.tsx").name, "typescript")
        self.assertEqual(self.config.language_for("handler.py").name, "python")
        self.assertIsNone(self.config.language_for("README.md"))

    def test_language_id_follows_the_file_kind(self):
        self.assertEqual(self.config.language_id("a.tsx"), "typescriptreact")
        self.assertEqual(self.config.language_id("a.mjs"), "javascript")

    def test_test_files_are_recognized_by_path(self):
        for path in ["app/test/x/core_test.clj", "src/a.spec.ts", "src/__tests__/a.ts", "pkg/test_api.py"]:
            self.assertTrue(self.config.is_test(path), path)
        self.assertFalse(self.config.is_test("src/attestation.ts"))

    def test_generated_files_never_show_their_diff(self):
        for path in ["package-lock.json", "web/pnpm-lock.yaml", "dist/app.js", "a.min.js"]:
            self.assertTrue(self.config.is_generated(path), path)
        self.assertFalse(self.config.is_generated("src/build_order.ts"))


if __name__ == "__main__":
    unittest.main()
