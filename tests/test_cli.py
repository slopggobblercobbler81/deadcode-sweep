"""Unit tests for deadcode-sweep CLI."""

import tempfile
import unittest
from pathlib import Path
from deadcode_sweep.cli import main


class TestCLI(unittest.TestCase):
    def test_cli_clean_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "clean.py"
            file_path.write_text("print('hello world')\n", encoding="utf-8")

            # Check mode should return 0
            code = main([str(file_path), "--check"])
            self.assertEqual(code, 0)

    def test_cli_deadcode_check_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "dirty.py"
            file_path.write_text("import sys\n", encoding="utf-8")

            # With --check, should return 1
            code = main([str(file_path), "--check"])
            self.assertEqual(code, 1)

            # Without --check, should return 0
            code = main([str(file_path)])
            self.assertEqual(code, 0)

    def test_cli_output_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "dirty.py"
            src_file.write_text("import sys\n", encoding="utf-8")
            out_file = Path(tmpdir) / "report.json"

            code = main([str(src_file), "--format", "json", "-o", str(out_file)])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())
            self.assertIn('"total_issues": 1', out_file.read_text(encoding="utf-8"))


    def test_cli_ignore_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "app.py"
            file_path.write_text("def _custom_hook():\n    return 1\n", encoding="utf-8")

            # Without ignore-names, _custom_hook is flagged
            code_without = main([str(file_path), "--check"])
            self.assertEqual(code_without, 1)

            # With ignore-names, passes
            code_with = main([str(file_path), "--check", "--ignore-names", "_custom_hook"])
            self.assertEqual(code_with, 0)


if __name__ == "__main__":
    unittest.main()
