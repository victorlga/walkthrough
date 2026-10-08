import unittest

import helpers  # noqa: F401
from walkthrough.symbols import assign_ids, innermost, node_candidates
from walkthrough.tokens import decode_semantic_tokens, linkable, regex_tokens, token_text, utf16_len


def rng(start, end, end_char=1):
    return {"start": {"line": start, "character": 0}, "end": {"line": end, "character": end_char}}


SYMBOLS = [
    {"name": "shop.pricing", "kind": 3, "range": rng(0, 40), "selectionRange": rng(0, 0), "children": [
        {"name": "Store", "kind": 5, "range": rng(2, 10), "selectionRange": rng(2, 2), "children": [
            {"name": "save", "kind": 6, "range": rng(4, 6), "selectionRange": rng(4, 4)},
        ]},
        {"name": "total", "kind": 12, "range": rng(12, 20), "selectionRange": rng(12, 12), "children": [
            {"name": "local_sum", "kind": 13, "range": rng(13, 13), "selectionRange": rng(13, 13)},
        ]},
        {"name": "discount", "kind": 12, "range": rng(22, 24), "selectionRange": rng(22, 22)},
        {"name": "discount", "kind": 12, "range": rng(26, 28, 0), "selectionRange": rng(26, 26)},
    ]},
]


class SymbolsTest(unittest.TestCase):
    def setUp(self):
        self.candidates = node_candidates(SYMBOLS)
        self.by_id = assign_ids("src/pricing.py", self.candidates)

    def test_top_level_and_class_members_are_nodes_but_function_locals_are_not(self):
        self.assertEqual([c.qualname for c in self.candidates], ["Store", "Store.save", "total", "discount", "discount"])

    def test_repeated_names_get_their_start_line(self):
        self.assertIn("src/pricing.py#Store.save", self.by_id)
        self.assertIn("src/pricing.py#discount:23", self.by_id)
        self.assertIn("src/pricing.py#discount:27", self.by_id)

    def test_innermost_node_wins(self):
        self.assertEqual(innermost(self.candidates, 6).qualname, "Store.save")
        self.assertEqual(innermost(self.candidates, 9).qualname, "Store")
        self.assertEqual(innermost(self.candidates, 14).qualname, "total")
        self.assertIsNone(innermost(self.candidates, 1))

    def test_a_range_ending_at_column_zero_stops_on_the_previous_line(self):
        last = self.by_id["src/pricing.py#discount:27"]
        self.assertEqual((last.start, last.end), (27, 28))


class TokensTest(unittest.TestCase):
    def test_semantic_tokens_decode_relative_positions(self):
        types = ["function", "parameter", "variable"]
        data = [2, 4, 5, 0, 0, 0, 7, 3, 1, 0, 1, 2, 4, 2, 0]
        tokens = decode_semantic_tokens(data, types)
        self.assertEqual([(t.line, t.col, t.length, t.kind) for t in tokens],
                         [(2, 4, 5, "function"), (2, 11, 3, "parameter"), (3, 2, 4, "variable")])
        self.assertEqual([t.kind for t in linkable(tokens)], ["function", "variable"])

    def test_columns_count_utf16_units_like_the_browser(self):
        line = 'x = "ação 😀"; total(y)'
        tokens = regex_tokens([line], "[A-Za-z_][A-Za-z0-9_]*", 0, 0)
        total = next(t for t in tokens if token_text(line, t.col, t.length) == "total")
        self.assertEqual(total.col, utf16_len('x = "ação 😀"; '))
        self.assertEqual(total.col, len('x = "ação 😀"; ') + 1)


if __name__ == "__main__":
    unittest.main()
