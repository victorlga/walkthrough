import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import git, init_repo
from walkthrough.cli import main
from walkthrough.review import ReviewError, build_review, hunk_lines

DIFF = """diff --git a/app/core.py b/app/core.py
--- a/app/core.py
+++ b/app/core.py
@@ -10,7 +10,8 @@ def total():
     a = 1
     b = 2
-    return a
+    c = 3
+    return a + c
     # end
@@ -40,0 +42,2 @@
+def extra():
+    pass
"""

REVIEW = {"walkthroughReview": 1, "pr": 7, "head": "abc123", "event": "COMMENT", "body": "Olhei o fluxo inteiro.",
          "comments": [{"path": "app/core.py", "line": 13, "body": "Por que c?"},
                       {"path": "app/core.py", "line": 30, "body": "Isto fica fora do diff."}]}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class ReviewTest(unittest.TestCase):
    def test_github_can_anchor_any_new_line_inside_a_diff_hunk(self):
        self.assertEqual(hunk_lines(DIFF), {"app/core.py": set(range(10, 18)) | {42, 43}})

    def test_comments_inside_the_diff_go_inline_and_the_rest_into_the_body(self):
        payload = build_review(REVIEW, {"app/core.py": set(range(10, 18))})
        self.assertEqual(payload["commit_id"], "abc123")
        self.assertEqual(payload["event"], "COMMENT")
        self.assertEqual(payload["comments"], [{"path": "app/core.py", "line": 13, "side": "RIGHT", "body": "Por que c?"}])
        self.assertIn("Olhei o fluxo inteiro.", payload["body"])
        self.assertIn("`app/core.py:30`", payload["body"])
        self.assertIn("Isto fica fora do diff.", payload["body"])

    def test_an_approval_may_have_no_text(self):
        payload = build_review({**REVIEW, "event": "APPROVE", "body": "", "comments": []}, {})
        self.assertEqual((payload["event"], payload["body"], payload["comments"]), ("APPROVE", "", []))

    def test_asking_for_changes_needs_some_text(self):
        with self.assertRaises(ReviewError):
            build_review({**REVIEW, "event": "REQUEST_CHANGES", "body": " ", "comments": []}, {})

    def test_an_unknown_verdict_is_refused(self):
        with self.assertRaises(ReviewError):
            build_review({**REVIEW, "event": "MERGE"}, {})


class ReviewCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        repo = init_repo(Path(self.tmp.name) / "repo")
        (repo / "app.py").write_text("".join(f"line {n}\n" for n in range(1, 31)))
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "base")
        base = git(repo, "rev-parse", "HEAD").strip()
        (repo / "app.py").write_text((repo / "app.py").read_text().replace("line 15\n", "line fifteen\n"))
        git(repo, "commit", "-am", "change")
        head = git(repo, "rev-parse", "HEAD").strip()
        self.review = {"walkthroughReview": 1, "pr": 7, "repoPath": str(repo), "base": base, "head": head,
                       "event": "COMMENT", "body": "", "comments": [{"path": "app.py", "line": 15, "body": "Bom nome."},
                                                                    {"path": "app.py", "line": 2, "body": "Longe."}]}
        self.file = Path(self.tmp.name) / "review.json"
        self.file.write_text(json.dumps(self.review))

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_prints_the_payload_without_posting(self):
        code, out, err = run("review", self.file, "--dry-run")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual([c["line"] for c in payload["comments"]], [15])
        self.assertIn("`app.py:2`", payload["body"])

    def test_a_block_that_is_not_a_walkthrough_review_is_refused(self):
        self.file.write_text(json.dumps({"pr": 7}))
        code, _, err = run("review", self.file, "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("not a walkthrough review", err)


if __name__ == "__main__":
    unittest.main()
