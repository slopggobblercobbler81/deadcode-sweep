"""Unit tests for Fixer."""

import tempfile
import unittest
from pathlib import Path
from deadcode_sweep.fixer import Fixer
from deadcode_sweep.models import Issue, IssueType, Location


class TestFixer(unittest.TestCase):
    def test_fix_python_entire_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "sample.py"
            file_path.write_text("import unused_mod\nprint('hello')\n", encoding="utf-8")

            issue = Issue(
                issue_type=IssueType.ORPHANED_IMPORT,
                location=Location(path=str(file_path), line=1),
                symbol="unused_mod",
                message="unused",
                fixable=True,
            )
            count = Fixer.fix_file(str(file_path), [issue])
            self.assertEqual(count, 1)

            fixed_content = file_path.read_text(encoding="utf-8")
            self.assertEqual(fixed_content, "print('hello')\n")

    def test_fix_python_partial_from_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "sample.py"
            file_path.write_text("from math import sin, cos\nprint(cos(0))\n", encoding="utf-8")

            issue = Issue(
                issue_type=IssueType.ORPHANED_IMPORT,
                location=Location(path=str(file_path), line=1),
                symbol="sin",
                message="unused",
                fixable=True,
            )
            count = Fixer.fix_file(str(file_path), [issue])
            self.assertEqual(count, 1)

            fixed_content = file_path.read_text(encoding="utf-8")
            self.assertEqual(fixed_content, "from math import cos\nprint(cos(0))\n")

    def test_fix_javascript_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "sample.js"
            file_path.write_text("import unusedMod from './unused';\nconsole.log('hi');\n", encoding="utf-8")

            issue = Issue(
                issue_type=IssueType.ORPHANED_IMPORT,
                location=Location(path=str(file_path), line=1),
                symbol="unusedMod",
                message="unused",
                fixable=True,
            )
            count = Fixer.fix_file(str(file_path), [issue])
            self.assertEqual(count, 1)

            fixed_content = file_path.read_text(encoding="utf-8")
            self.assertEqual(fixed_content, "console.log('hi');\n")


    def test_fix_python_multi_name_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "sample.py"
            file_path.write_text("import sys, os\nprint(os.name)\n", encoding="utf-8")

            issue = Issue(
                issue_type=IssueType.ORPHANED_IMPORT,
                location=Location(path=str(file_path), line=1),
                symbol="sys",
                message="unused",
                fixable=True,
            )
            count = Fixer.fix_file(str(file_path), [issue])
            self.assertEqual(count, 1)

            fixed_content = file_path.read_text(encoding="utf-8")
            self.assertEqual(fixed_content, "import os\nprint(os.name)\n")


if __name__ == "__main__":
    unittest.main()
