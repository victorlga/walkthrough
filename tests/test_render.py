import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from walkthrough.render import render


def node(node_id, depth, up, direction, links=()):
    path = node_id.split("#")[0]
    return {"id": node_id, "name": node_id.split("#")[1], "qualname": node_id.split("#")[1], "kind": "function",
            "path": path, "language": "python", "lines": [1, 2], "source": "def f():\n    return '</script>'",
            "change": {"status": "modified" if direction == "seed" else "unchanged", "added": [], "removed": []},
            "links": [{"line": 2, "col": 4, "len": 6, "to": t} for t in links], "external": [], "callers": [],
            "callersComputed": True, "implementations": [], "depth": depth, "up": up, "direction": direction,
            "test": False}


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name)
        nodes = {"a.py#seed": node("a.py#seed", 0, 0, "seed", links=["b.py#near"]),
                 "b.py#near": node("b.py#near", 1, 0, "down", links=["c.py#far"]),
                 "c.py#far": node("c.py#far", 6, 0, "down")}
        index = {"meta": {"repo": "demo", "label": "feature", "slug": "feature", "title": "Feature"}, "files": {},
                 "nodes": nodes, "hunks": [], "changed": ["a.py#seed"], "entryPoints": [], "testEntryPoints": [],
                 "impact": {}, "parts": [["a.py#seed"]], "signals": {}, "lostLinks": [], "truncated": {"maxNodesHit": False}}
        (self.run_dir / "index.json").write_text(json.dumps(index))
        (self.run_dir / "plan.json").write_text(json.dumps({"parts": [{"title": "Parte", "roteiro": ["a.py#seed"]}],
                                                            "skeleton": ["a.py#seed"], "other": [], "mechanical": {"summary": "", "paths": []}}))
        (self.run_dir / "explanations.json").write_text(json.dumps({"overview": {"story": "História.", "glossaryDivergences": []},
                                                                    "nodes": {}, "pruned": []}))

    def tearDown(self):
        self.tmp.cleanup()

    def data_of(self, html):
        raw = re.search(r'<script id="walkthrough-data" type="application/json">(.*?)</script>', html, re.S).group(1)
        return json.loads(raw)

    def test_artifact_mode_starts_with_the_title_and_has_no_document_skeleton(self):
        out = self.run_dir / "page.html"
        render(self.run_dir, out, mode="artifact", lang="pt")
        html = out.read_text()
        self.assertTrue(html.startswith("<title>feature walkthrough</title>"))
        self.assertNotIn("<!doctype", html.lower())
        self.assertEqual(self.data_of(html)["index"]["meta"]["slug"], "feature")

    def test_source_text_cannot_close_the_data_script(self):
        out = self.run_dir / "page.html"
        render(self.run_dir, out)
        raw = re.search(r'<script id="walkthrough-data" type="application/json">(.*?)</script>', out.read_text(), re.S).group(1)
        self.assertNotIn("</script>", raw)
        self.assertEqual(self.data_of(out.read_text())["index"]["nodes"]["a.py#seed"]["source"].split("\n")[1], "    return '</script>'")

    def test_local_mode_is_a_full_document(self):
        out = self.run_dir / "local.html"
        render(self.run_dir, out, mode="local", lang="en")
        html = out.read_text()
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertTrue(html.rstrip().endswith("</body></html>"))

    def test_oversized_pages_drop_the_farthest_functions_first(self):
        out = self.run_dir / "small.html"
        full = render(self.run_dir, out)["bytes"]
        result = render(self.run_dir, out, max_bytes=full - 10)
        data = self.data_of(out.read_text())
        self.assertEqual(result["trimmed"], 1)
        self.assertEqual(sorted(data["index"]["nodes"]), ["a.py#seed", "b.py#near"])
        near_link = data["index"]["nodes"]["b.py#near"]["links"][0]
        self.assertEqual((near_link.get("to"), near_link["path"], near_link["targetLine"]), (None, "c.py", 1))
        self.assertEqual(data["index"]["truncated"]["trimmedForSize"], 1)


if __name__ == "__main__":
    unittest.main()
