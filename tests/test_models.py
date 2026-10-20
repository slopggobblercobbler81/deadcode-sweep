"""Unit tests for deadcode-sweep models."""

import unittest
from deadcode_sweep.models import (
    AnalysisResult,
    Issue,
    IssueType,
    Location,
    ProjectContext,
    Report,
    Severity,
)


class TestModels(unittest.TestCase):
    def test_location_string(self):
        loc1 = Location(path="foo.py", line=10, col=5)
        self.assertEqual(str(loc1), "foo.py:10:5")

        loc2 = Location(path="foo.py", line=10, col=5, end_line=12, end_col=8)
        self.assertEqual(str(loc2), "foo.py:10:5-12:8")

    def test_location_dict(self):
        loc = Location(path="foo.py", line=1, col=2, end_line=3, end_col=4)
        d = loc.to_dict()
        self.assertEqual(d["path"], "foo.py")
        self.assertEqual(d["line"], 1)
        self.assertEqual(d["col"], 2)
        self.assertEqual(d["end_line"], 3)
        self.assertEqual(d["end_col"], 4)

    def test_severity_levels(self):
        self.assertLess(Severity.INFO.level, Severity.WARNING.level)
        self.assertLess(Severity.WARNING.level, Severity.ERROR.level)

    def test_issue_serialization(self):
        loc = Location(path="app.py", line=5, col=1)
        issue = Issue(
            issue_type=IssueType.ORPHANED_IMPORT,
            location=loc,
            symbol="sys",
            message="Unused import",
            severity=Severity.WARNING,
            details="import sys",
            fixable=True,
        )
        d = issue.to_dict()
        self.assertEqual(d["type"], "orphaned_import")
        self.assertEqual(d["symbol"], "sys")
        self.assertTrue(d["fixable"])
        self.assertEqual(d["severity"], "warning")

    def test_project_context(self):
        ctx = ProjectContext()
        ctx.register_reference("helper", "main.py")
        self.assertTrue(ctx.is_symbol_referenced("helper"))
        self.assertFalse(ctx.is_symbol_referenced("unknown"))
        self.assertTrue(ctx.is_symbol_referenced("helper", exclude_file="other.py"))
        self.assertFalse(ctx.is_symbol_referenced("helper", exclude_file="main.py"))

        loc = Location(path="utils.py", line=10, col=1)
        ctx.register_function("helper", "utils.py", loc)
        self.assertIn(("utils.py", "helper"), ctx.defined_functions)

    def test_report_aggregates(self):
        loc = Location(path="app.py", line=1)
        i1 = Issue(IssueType.ORPHANED_IMPORT, loc, "os", "unused")
        i2 = Issue(IssueType.UNUSED_FUNCTION, loc, "foo", "unused")
        i3 = Issue(IssueType.UNREACHABLE_CODE, loc, "<dead>", "unreachable", severity=Severity.ERROR)

        res1 = AnalysisResult(file_path="app.py", issues=[i1, i2], lines_scanned=50)
        res2 = AnalysisResult(file_path="other.py", issues=[i3], lines_scanned=20)

        report = Report(results=[res1, res2], total_files=2, total_lines=70, duration_seconds=0.1)

        self.assertEqual(report.total_issues, 3)
        self.assertTrue(report.has_errors())
        counts = report.issues_by_type()
        self.assertEqual(counts["orphaned_import"], 1)
        self.assertEqual(counts["unused_function"], 1)
        self.assertEqual(counts["unreachable_code"], 1)

        d = report.to_dict()
        self.assertEqual(d["summary"]["total_files"], 2)
        self.assertEqual(d["summary"]["total_issues"], 3)


if __name__ == "__main__":
    unittest.main()
