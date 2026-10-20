"""Unit tests for PythonAnalyzer."""

import unittest
from deadcode_sweep.analyzers.python_analyzer import PythonAnalyzer
from deadcode_sweep.models import IssueType, ProjectContext, Severity


class TestPythonAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = PythonAnalyzer()

    def test_unused_import_simple(self):
        code = "import sys\nimport os\nprint(os.name)\n"
        res = self.analyzer.analyze_code(code, "test.py")
        self.assertEqual(len(res.issues), 1)
        issue = res.issues[0]
        self.assertEqual(issue.issue_type, IssueType.ORPHANED_IMPORT)
        self.assertEqual(issue.symbol, "sys")
        self.assertEqual(issue.location.line, 1)

    def test_unused_from_import(self):
        code = "from math import sin, cos\nprint(sin(1.0))\n"
        res = self.analyzer.analyze_code(code, "test.py")
        self.assertEqual(len(res.issues), 1)
        self.assertEqual(res.issues[0].symbol, "cos")

    def test_aliased_import_usage(self):
        code = "import numpy as np\nprint(np.zeros(5))\n"
        res = self.analyzer.analyze_code(code, "test.py")
        self.assertEqual(len(res.issues), 0)

    def test_unused_aliased_import(self):
        code = "import numpy as np\nprint('hello')\n"
        res = self.analyzer.analyze_code(code, "test.py")
        self.assertEqual(len(res.issues), 1)
        self.assertEqual(res.issues[0].symbol, "np")

    def test_dunder_all_exports_import(self):
        code = "from utils import helper\n__all__ = ['helper']\n"
        res = self.analyzer.analyze_code(code, "test.py")
        self.assertEqual(len(res.issues), 0)

    def test_unreachable_after_return(self):
        code = (
            "def calc(x):\n"
            "    if x > 0:\n"
            "        return x * 2\n"
            "        print('never reached')\n"
            "    return 0\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 4)

    def test_unreachable_after_raise(self):
        code = (
            "def fail():\n"
            "    raise ValueError('error')\n"
            "    cleanup()\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 3)

    def test_unreachable_after_sys_exit(self):
        code = (
            "import sys\n"
            "def stop():\n"
            "    sys.exit(1)\n"
            "    print('post exit')\n"
            "stop()\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 4)

    def test_dead_branch_if_false(self):
        code = (
            "def run():\n"
            "    if False:\n"
            "        dead_code()\n"
            "    return True\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].symbol, "<dead-branch>")

    def test_dead_loop_while_false(self):
        code = (
            "while False:\n"
            "    do_something()\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].symbol, "<dead-loop>")

    def test_unused_private_function(self):
        code = (
            "def _internal_helper():\n"
            "    return 42\n"
            "def public_api():\n"
            "    return 'ok'\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unused = [i for i in res.issues if i.issue_type == IssueType.UNUSED_FUNCTION]
        self.assertEqual(len(unused), 1)
        self.assertEqual(unused[0].symbol, "_internal_helper")

    def test_used_private_function(self):
        code = (
            "def _internal_helper():\n"
            "    return 42\n"
            "def public_api():\n"
            "    return _internal_helper()\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unused = [i for i in res.issues if i.issue_type == IssueType.UNUSED_FUNCTION]
        self.assertEqual(len(unused), 0)

    def test_ignored_decorator_and_dunder(self):
        code = (
            "class MyClass:\n"
            "    def __init__(self):\n"
            "        self._val = 1\n"
            "    @property\n"
            "    def val(self):\n"
            "        return self._val\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unused = [i for i in res.issues if i.issue_type == IssueType.UNUSED_FUNCTION]
        self.assertEqual(len(unused), 0)

    def test_syntax_error_reported(self):
        code = "def broken(\n"
        res = self.analyzer.analyze_code(code, "broken.py")
        self.assertIsNotNone(res.parse_error)
        self.assertEqual(len(res.issues), 1)
        self.assertEqual(res.issues[0].severity, Severity.ERROR)

    def test_multi_file_context(self):
        ctx = ProjectContext()
        file1 = "utils.py"
        code1 = "def shared_func():\n    return 1\n"
        self.analyzer.collect_symbols(code1, file1, ctx)

        file2 = "main.py"
        code2 = "import utils\nprint(utils.shared_func())\n"
        self.analyzer.collect_symbols(code2, file2, ctx)

        res1 = self.analyzer.analyze_code(code1, file1, context=ctx)
        unused1 = [i for i in res1.issues if i.issue_type == IssueType.UNUSED_FUNCTION]
        # shared_func is referenced in main.py, so not unused
        self.assertEqual(len(unused1), 0)


    def test_unreachable_in_except_handler(self):
        code = (
            "def handle():\n"
            "    try:\n"
            "        do_something()\n"
            "    except Exception:\n"
            "        raise RuntimeError('failed')\n"
            "        print('unreachable in handler')\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 6)

    def test_unreachable_in_loop_after_break(self):
        code = (
            "for i in range(10):\n"
            "    break\n"
            "    print('dead after break')\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 3)

    def test_unreachable_in_loop_after_continue(self):
        code = (
            "for i in range(10):\n"
            "    continue\n"
            "    print('dead after continue')\n"
        )
        res = self.analyzer.analyze_code(code, "test.py")
        unreachable = [i for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0].location.line, 3)


if __name__ == "__main__":
    unittest.main()
