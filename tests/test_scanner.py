"""Unit tests for Scanner."""

import tempfile
import unittest
from pathlib import Path
from deadcode_sweep.models import IssueType
from deadcode_sweep.scanner import Scanner


class TestScanner(unittest.TestCase):
    def test_scanner_discovery_and_scan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "a.py").write_text("import sys\n", encoding="utf-8")
            (p / "b.js").write_text("const x = require('fs');\n", encoding="utf-8")

            # Create ignored directory
            node_modules = p / "node_modules"
            node_modules.mkdir()
            (node_modules / "bad.js").write_text("const z = require('bad');\n", encoding="utf-8")

            scanner = Scanner(lang="all")
            report = scanner.scan([str(p)])

            self.assertEqual(report.total_files, 2)
            self.assertEqual(report.total_issues, 2)

    def test_scanner_lang_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "a.py").write_text("import sys\n", encoding="utf-8")
            (p / "b.js").write_text("const x = require('fs');\n", encoding="utf-8")

            scanner = Scanner(lang="python")
            report = scanner.scan([str(p)])
            self.assertEqual(report.total_files, 1)
            self.assertTrue(report.results[0].file_path.endswith("a.py"))

    def test_scanner_with_autofix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            test_file = p / "test.py"
            test_file.write_text("import unused_foo\nprint('hello')\n", encoding="utf-8")

            scanner = Scanner(lang="python", fix=True)
            report = scanner.scan([str(p)])

            self.assertEqual(report.fixed_count, 1)
            self.assertEqual(test_file.read_text(encoding="utf-8"), "print('hello')\n")


if __name__ == "__main__":
    unittest.main()
