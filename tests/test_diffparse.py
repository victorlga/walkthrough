import tempfile
import unittest
from pathlib import Path

from helpers import git, init_repo
from walkthrough.diffparse import parse_diff


class DiffParseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        repo = init_repo(Path(self.tmp.name) / "repo")
        (repo / "a.txt").write_text("".join(f"{n}\n" for n in range(1, 11)))
        (repo / "b.txt").write_text("gone\nfor good\n")
        (repo / "d.txt").write_text("".join(f"line {n}\n" for n in range(1, 21)))
        (repo / "img.bin").write_bytes(b"\x00\x01\x02")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "base")
        a = [str(n) for n in range(1, 11)]
        a[2] = "three"
        del a[5:7]
        a.insert(a.index("9") + 1, "9a")
        a.insert(a.index("9a") + 1, "9b")
        (repo / "a.txt").write_text("\n".join(a) + "\n")
        (repo / "b.txt").unlink()
        (repo / "c.txt").write_text("new\nfile\n")
        git(repo, "mv", "d.txt", "e.txt")
        (repo / "e.txt").write_text((repo / "e.txt").read_text().replace("line 10\n", "line ten\n"))
        (repo / "img.bin").write_bytes(b"\x00\x09\x02")
        git(repo, "add", "-A")
        text = git(repo, "diff", "--no-color", "--no-ext-diff", "-U0", "-M", "--cached", "HEAD")
        self.files = {f.path: f for f in parse_diff(text)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_replaced_deleted_and_inserted_lines_land_on_new_side_numbers(self):
        a = self.files["a.txt"]
        self.assertEqual(a.status, "modified")
        self.assertEqual(a.added, [3, 8, 9])
        self.assertEqual([(b.after, b.lines) for b in a.removed], [(2, ["3"]), (5, ["6", "7"])])
        self.assertEqual(a.removed_count, 3)

    def test_deleted_file_keeps_its_path_and_text(self):
        b = self.files["b.txt"]
        self.assertEqual(b.status, "deleted")
        self.assertEqual(b.removed[0].lines, ["gone", "for good"])
        self.assertEqual(b.added, [])

    def test_added_file_has_every_line_added(self):
        c = self.files["c.txt"]
        self.assertEqual(c.status, "added")
        self.assertEqual(c.added, [1, 2])

    def test_rename_keeps_the_old_path(self):
        e = self.files["e.txt"]
        self.assertEqual(e.status, "renamed")
        self.assertEqual(e.old_path, "d.txt")
        self.assertEqual(e.added, [10])

    def test_binary_file_has_no_lines(self):
        img = self.files["img.bin"]
        self.assertEqual(img.status, "binary")
        self.assertEqual(img.added, [])


if __name__ == "__main__":
    unittest.main()
