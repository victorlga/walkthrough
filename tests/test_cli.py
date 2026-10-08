import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, init_repo, make_fixture_repo
from walkthrough.cli import main, short_list
from walkthrough.config import Language


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_fixture_repo("python", cls.tmp.name)
        cls.run_dir = Path(cls.tmp.name) / "run"
        cls.code, cls.out, cls.err = run("index", "--repo", cls.repo, "--base", "main", "--run-dir", cls.run_dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_index_writes_the_index_and_the_context(self):
        self.assertEqual(self.code, 0, self.err)
        self.assertEqual(self.out.splitlines()[0], str(self.run_dir))
        self.assertIn("app/pricing.py#base_price", json.loads((self.run_dir / "index.json").read_text())["nodes"])
        self.assertEqual(json.loads((self.run_dir / "context.json").read_text())["commits"], ["change"])

    def test_summary_lists_changed_functions_with_their_signals(self):
        code, out, _ = run("summary", self.run_dir)
        self.assertEqual(code, 0)
        self.assertIn("app/pricing.py#base_price | modified", out)
        self.assertIn("entry points: app/api.py#handler", out)

    def test_long_lists_in_the_summary_show_fifteen_and_a_count(self):
        self.assertEqual(short_list([f"e{n}" for n in range(20)]), ", ".join(f"e{n}" for n in range(15)) + " (+5 more)")
        self.assertEqual(short_list([]), "none")

    def test_context_shows_numbered_source_with_diff_marks_and_callers(self):
        code, out, _ = run("context", self.run_dir, "app/pricing.py#base_price")
        self.assertEqual(code, 0)
        self.assertIn("  14 +     note", out)
        self.assertIn("tests/test_pricing.py#test_base_price (test)", out)

    def test_doctor_names_the_languages_in_the_diff(self):
        code, out, _ = run("doctor", "--repo", self.repo, "--base", "main")
        self.assertEqual(code, 0)
        self.assertIn("languages in the diff: python", out)

    def test_missing_server_stops_with_the_install_command(self):
        with mock.patch.object(Language, "installed", lambda self: False):
            code, _, err = run("index", "--repo", self.repo, "--base", "main", "--run-dir", Path(self.tmp.name) / "x")
        self.assertEqual(code, 2)
        self.assertIn("npm install -g basedpyright", err)

    def test_skipping_a_language_turns_its_changes_into_hunks(self):
        run_dir = Path(self.tmp.name) / "skip"
        with mock.patch.object(Language, "installed", lambda self: False):
            code, _, err = run("index", "--repo", self.repo, "--base", "main", "--run-dir", run_dir,
                               "--skip-language", "python")
        self.assertEqual(code, 0, err)
        index = json.loads((run_dir / "index.json").read_text())
        self.assertEqual(index["nodes"], {})
        self.assertIn("app/pricing.py", {h["path"] for h in index["hunks"]})

    def test_cleanup_removes_the_worktree_of_another_branch(self):
        git(self.repo, "branch", "other")
        run_dir = Path(self.tmp.name) / "other"
        code, _, err = run("index", "other", "--repo", self.repo, "--base", "main", "--run-dir", run_dir)
        self.assertEqual(code, 0, err)
        self.assertTrue((run_dir / "worktree").exists())
        self.assertEqual(run("cleanup", run_dir)[0], 0)
        self.assertFalse((run_dir / "worktree").exists())


    def test_cleanup_refuses_a_worktree_folder_git_did_not_create(self):
        project = init_repo(Path(self.tmp.name) / "project")
        (project / "worktree").mkdir()
        (project / "worktree" / "notes.txt").write_text("mine")
        git(project, "add", "-A")
        git(project, "commit", "-m", "notes")
        code, _, err = run("cleanup", project)
        self.assertEqual(code, 1)
        self.assertIn("not a walkthrough worktree", err)
        self.assertTrue((project / "worktree" / "notes.txt").exists())

    def test_a_failed_index_leaves_no_worktree_behind(self):
        git(self.repo, "branch", "broken")
        run_dir = Path(self.tmp.name) / "broken"
        with mock.patch.object(Language, "installed", lambda self: False):
            code, _, _ = run("index", "broken", "--repo", self.repo, "--base", "main", "--run-dir", run_dir)
        self.assertEqual(code, 2)
        self.assertFalse((run_dir / "worktree").exists())
        self.assertNotIn(str(run_dir), git(self.repo, "worktree", "list"))

    def test_indexing_again_drops_the_previous_explanations(self):
        run_dir = Path(self.tmp.name) / "again"
        self.assertEqual(run("index", "--repo", self.repo, "--base", "main", "--run-dir", run_dir)[0], 0)
        (run_dir / "explanations.json").write_text("{}")
        (run_dir / "plan.json").write_text("{}")
        (run_dir / "fragments").mkdir()
        (run_dir / "fragments" / "old.json").write_text("{}")
        self.assertEqual(run("index", "--repo", self.repo, "--base", "main", "--run-dir", run_dir)[0], 0)
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()), ["context.json", "index.json"])


if __name__ == "__main__":
    unittest.main()
