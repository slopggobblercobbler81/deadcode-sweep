"""Unit tests for Formatter."""

import json
import unittest
from deadcode_sweep.formatter import Formatter
from deadcode_sweep.models import (
    AnalysisResult,
    Issue,
    IssueType,
    Location,
    Report,
    Severity,
)


class TestFormatter(unittest.TestCase):
    def setUp(self):
        loc = Location(path="src/main.py", line=10, col=2)
        issue1 = Issue(
            issue_type=IssueType.ORPHANED_IMPORT,
            location=loc,
            symbol="os",
            message="Imported symbol 'os' is never used",
            severity=Severity.WARNING,
        )
        issue2 = Issue(
            issue_type=IssueType.UNREACHABLE_CODE,
            location=Location(path="src/main.py", line=25, col=1),
            symbol="<unreachable>",
            message="Code following return is unreachable",
            severity=Severity.ERROR,
        )
        res = AnalysisResult(
            file_path="src/main.py",
            issues=[issue1, issue2],
            lines_scanned=30,
        )
        self.report = Report(
            results=[res],
            total_files=1,
            total_lines=30,
            duration_seconds=0.05,
        )

    def test_text_formatter(self):
        txt = Formatter.format(self.report, fmt="text", no_color=True)
        self.assertIn("deadcode-sweep", txt)
        self.assertIn("src/main.py", txt)
        self.assertIn("Imported symbol 'os' is never used", txt)
        self.assertIn("Files scanned: 1", txt)

    def test_json_formatter(self):
        json_str = Formatter.format(self.report, fmt="json")
        data = json.loads(json_str)
        self.assertEqual(data["summary"]["total_files"], 1)
        self.assertEqual(data["summary"]["total_issues"], 2)
        self.assertEqual(len(data["results"]), 1)

    def test_csv_formatter(self):
        csv_str = Formatter.format(self.report, fmt="csv")
        lines = csv_str.strip().splitlines()
        self.assertGreaterEqual(len(lines), 3)  # header + 2 issues
        self.assertIn("orphaned_import", lines[1])

    def test_github_formatter(self):
        gh_str = Formatter.format(self.report, fmt="github")
        self.assertIn("::warning file=src/main.py,line=10,col=2::", gh_str)
        self.assertIn("::error file=src/main.py,line=25,col=1::", gh_str)

    def test_summary_formatter(self):
        sum_str = Formatter.format(self.report, fmt="summary", no_color=True)
        self.assertIn("src/main.py", sum_str)
        self.assertIn("TOTAL", sum_str)

    def test_min_severity_filter(self):
        txt = Formatter.format(self.report, fmt="text", min_severity="error", no_color=True)
        self.assertNotIn("Imported symbol 'os' is never used", txt)
        self.assertIn("Code following return is unreachable", txt)


if __name__ == "__main__":
    unittest.main()
