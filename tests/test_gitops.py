import tempfile
import unittest
from pathlib import Path

from helpers import git, init_repo
from walkthrough import gitops


class GitopsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        origin = base / "origin.git"
        git(base, "init", "--bare", "-b", "main", str(origin))
        self.repo = init_repo(base / "repo")
        (self.repo / "app.py").write_text("def a():\n    return 1\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "remote", "add", "origin", str(origin))
        git(self.repo, "push", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "checkout", "-b", "other")
        (self.repo / "app.py").write_text("def a():\n    return 2\n")
        git(self.repo, "commit", "-am", "other change")
        git(self.repo, "checkout", "-b", "feature", "main")
        (self.repo / "app.py").write_text("def a():\n    return 3\n")
        (self.repo / "new.py").write_text("def b():\n    return 4\n")
        self.run_dir = base / "run"

    def tearDown(self):
        self.tmp.cleanup()

    def test_main_branch_comes_from_origin_head(self):
        self.assertEqual(gitops.default_base(self.repo), "origin/main")

    def test_without_origin_head_the_user_must_pass_a_base(self):
        git(self.repo, "remote", "set-head", "origin", "--delete")
        with self.assertRaises(gitops.GitError) as error:
            gitops.default_base(self.repo)
        self.assertIn("--base", str(error.exception))

    def test_current_branch_includes_uncommitted_and_untracked_changes(self):
        target = gitops.resolve_target(self.repo, None, None, self.run_dir)
        self.assertEqual(target.root, self.repo.resolve())
        self.assertIsNone(target.worktree)
        self.assertEqual(target.slug, "feature")
        self.assertIn("return 3", gitops.diff_text(target.root, target.base_sha))
        self.assertIn("new.py", gitops.untracked_files(target.root))
        self.assertIn("new.py", gitops.repo_files(target.root))

    def test_unrelated_history_asks_for_a_base_and_leaves_no_worktree(self):
        git(self.repo, "checkout", "--orphan", "unrelated")
        git(self.repo, "rm", "-rf", "--cached", ".")
        (self.repo / "other.py").write_text("x = 1\n")
        git(self.repo, "add", "other.py")
        git(self.repo, "commit", "-m", "unrelated root")
        git(self.repo, "checkout", "-f", "feature")
        with self.assertRaises(gitops.GitError) as error:
            gitops.resolve_target(self.repo, "unrelated", None, self.run_dir)
        self.assertIn("no common history", str(error.exception))
        self.assertIn("--base", str(error.exception))
        self.assertFalse((self.run_dir / "worktree").exists())

    def test_a_linked_worktree_is_named_after_its_main_repo(self):
        linked = self.run_dir.parent / "some-worktree-name"
        git(self.repo, "worktree", "add", str(linked), "other")
        self.assertEqual(gitops.repo_name(linked), "repo")
        self.assertEqual(gitops.repo_name(self.repo), "repo")

    def test_other_branch_gets_a_temporary_worktree_that_cleanup_removes(self):
        target = gitops.resolve_target(self.repo, "other", None, self.run_dir)
        self.assertEqual(target.worktree, (self.run_dir / "worktree").resolve())
        self.assertIn("return 2", (target.root / "app.py").read_text())
        self.assertIn("return 2", gitops.diff_text(target.root, target.base_sha))
        gitops.remove_worktree(self.repo, target.worktree)
        self.assertFalse(target.worktree.exists())
        self.assertNotIn(str(target.worktree), git(self.repo, "worktree", "list"))


if __name__ == "__main__":
    unittest.main()
