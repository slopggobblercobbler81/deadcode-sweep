"""Unit tests for JavaScriptAnalyzer."""

import unittest
from deadcode_sweep.analyzers.javascript_analyzer import JavaScriptAnalyzer
from deadcode_sweep.models import IssueType, ProjectContext


class TestJavaScriptAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = JavaScriptAnalyzer()

    def test_unused_es6_import(self):
        code = "import { foo, bar } from './math';\nconsole.log(foo);\n"
        res = self.analyzer.analyze_code(code, "index.js")
        orphaned = [i for i in res.issues if i.issue_type == IssueType.ORPHANED_IMPORT]
        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0].symbol, "bar")

    def test_unused_cjs_import(self):
        code = "const fs = require('fs');\nconst path = require('path');\nconsole.log(path.join('a', 'b'));\n"
        res = self.analyzer.analyze_code(code, "index.js")
        orphaned = [i for i in res.issues if i.issue_type == IssueType.ORPHANED_IMPORT]
        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0].symbol, "fs")

    def test_unreachable_after_return(self):
        code = (
            "function compute(x) {\n"
            "  if (x > 0) {\n"
            "    return x * 2;\n"
            "    console.log('dead');\n"
            "  }\n"
            "  return 0;\n"
            "}\n"
        )
        res = self.analyzer.analyze_code(code, "index.js")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 4)

    def test_unreachable_after_throw(self):
        code = (
            "function validate(x) {\n"
            "  if (!x) {\n"
            "    throw new Error('missing');\n"
            "    cleanup();\n"
            "  }\n"
            "}\n"
        )
        res = self.analyzer.analyze_code(code, "index.js")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 4)

    def test_dead_branch_if_false(self):
        code = (
            "if (false) {\n"
            "  console.log('never runs');\n"
            "}\n"
        )
        res = self.analyzer.analyze_code(code, "index.js")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].symbol, "<dead-branch>")

    def test_unused_unexported_function(self):
        code = (
            "function helper() {\n"
            "  return 1;\n"
            "}\n"
            "export function main() {\n"
            "  return 2;\n"
            "}\n"
        )
        res = self.analyzer.analyze_code(code, "index.js")
        unused = [i for i in res.issues if i.issue_type == IssueType.UNUSED_FUNCTION]
        self.assertEqual(len(unused), 1)
        self.assertEqual(unused[0].symbol, "helper")

    def test_used_internal_function(self):
        code = (
            "function helper() {\n"
            "  return 1;\n"
            "}\n"
            "export function main() {\n"
            "  return helper() + 2;\n"
            "}\n"
        )
        res = self.analyzer.analyze_code(code, "index.js")
        unused = [i for i in res.issues if i.issue_type == IssueType.UNUSED_FUNCTION]
        self.assertEqual(len(unused), 0)

    def test_comments_and_strings_ignored(self):
        # Even if 'foo' is in comment or string, it should not count as real code usage
        code = (
            "import { foo } from './foo';\n"
            "// foo is commented out\n"
            "const str = 'foo in string';\n"
        )
        res = self.analyzer.analyze_code(code, "index.js")
        orphaned = [i for i in res.issues if i.issue_type == IssueType.ORPHANED_IMPORT]
        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0].symbol, "foo")


if __name__ == "__main__":
    unittest.main()
