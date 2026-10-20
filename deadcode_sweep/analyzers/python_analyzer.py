"""AST-based static analyzer for Python codebases."""

import ast
from typing import List, Optional, Set, Tuple

from deadcode_sweep.analyzers.base import BaseAnalyzer
from deadcode_sweep.models import (
    AnalysisResult,
    Issue,
    IssueType,
    Location,
    ProjectContext,
    Severity,
)

COMMON_FRAMEWORK_DECORATORS = {
    "property",
    "setter",
    "deleter",
    "classmethod",
    "staticmethod",
    "abstractmethod",
    "fixture",
    "route",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "command",
    "group",
    "hookimpl",
    "receiver",
}

COMMON_IGNORED_NAMES = {
    "main",
    "run",
    "setup",
    "teardown",
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "setUpModule",
    "tearDownModule",
}


def _is_terminal_statement(node: ast.AST) -> Tuple[bool, str]:
    """Check if an AST statement terminates execution in its block."""
    if isinstance(node, ast.Return):
        return True, "return"
    if isinstance(node, ast.Raise):
        return True, "raise"
    if isinstance(node, ast.Break):
        return True, "break"
    if isinstance(node, ast.Continue):
        return True, "continue"
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
        # Check for sys.exit, os._exit, exit, quit
        if isinstance(call.func, ast.Name) and call.func.id in ("exit", "quit"):
            return True, f"{call.func.id}()"
        if isinstance(call.func, ast.Attribute):
            attr_name = call.func.attr
            if isinstance(call.func.value, ast.Name):
                mod_name = call.func.value.id
                if (mod_name == "sys" and attr_name == "exit") or (
                    mod_name == "os" and attr_name in ("_exit", "abort")
                ):
                    return True, f"{mod_name}.{attr_name}()"
    return False, ""


def _is_constant_false(node: ast.AST) -> bool:
    """Check if expression evaluates statically to False."""
    if isinstance(node, ast.Constant):
        return bool(node.value) is False
    return False


def _is_constant_true(node: ast.AST) -> bool:
    """Check if expression evaluates statically to True."""
    if isinstance(node, ast.Constant):
        return bool(node.value) is True
    return False


class PythonAnalyzer(BaseAnalyzer):
    """Static analyzer for Python source files using standard library `ast`."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def supported_extensions(self) -> Tuple[str, ...]:
        return (".py", ".pyw", ".pyi")

    def collect_symbols(
        self,
        code: str,
        file_path: str,
        context: ProjectContext,
    ) -> None:
        """Pass 1: Collect definitions and symbol usages for project-wide analysis."""
        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError:
            return

        # Find exported symbols if __all__ is present
        all_exports: Set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    all_exports.add(elt.value)
                                    context.exported_symbols.add(elt.value)

        # Collect function definitions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_name = node.name
                if not fn_name.startswith("__") or not fn_name.endswith("__"):
                    loc = Location(
                        path=file_path,
                        line=node.lineno,
                        col=node.col_offset + 1,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        end_col=getattr(node, "end_col_offset", None),
                    )
                    context.register_function(fn_name, file_path, loc)

            # Collect symbol references
            if isinstance(node, ast.Name):
                context.register_reference(node.id, file_path)
            elif isinstance(node, ast.Attribute):
                context.register_reference(node.attr, file_path)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # String forward-ref or name in __all__
                if node.value.isidentifier():
                    context.register_reference(node.value, file_path)

    def analyze_code(
        self,
        code: str,
        file_path: str,
        context: Optional[ProjectContext] = None,
        ignore_names: Optional[Set[str]] = None,
        include_public_functions: bool = False,
    ) -> AnalysisResult:
        """Analyze Python source code for dead code issues."""
        lines = code.splitlines()
        lines_scanned = len(lines)
        ignored = (ignore_names or set()) | COMMON_IGNORED_NAMES

        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            err_loc = Location(
                path=file_path,
                line=e.lineno or 1,
                col=e.offset or 1,
            )
            issue = Issue(
                issue_type=IssueType.UNREACHABLE_CODE,
                location=err_loc,
                symbol="<syntax-error>",
                message=f"SyntaxError parsing file: {e.msg}",
                severity=Severity.ERROR,
            )
            return AnalysisResult(
                file_path=file_path,
                issues=[issue],
                lines_scanned=lines_scanned,
                parse_error=str(e),
            )

        issues: List[Issue] = []

        # 1. Detect orphaned imports
        issues.extend(self._find_orphaned_imports(tree, file_path))

        # 2. Detect unreachable code
        issues.extend(self._find_unreachable_code(tree, file_path))

        # 3. Detect unused functions
        issues.extend(
            self._find_unused_functions(
                tree,
                file_path,
                context=context,
                ignore_names=ignored,
                include_public_functions=include_public_functions,
            )
        )

        # Sort issues by line number
        issues.sort(key=lambda x: (x.location.line, x.location.col))
        return AnalysisResult(
            file_path=file_path,
            issues=issues,
            lines_scanned=lines_scanned,
        )

    def _find_orphaned_imports(self, tree: ast.Module, file_path: str) -> List[Issue]:
        """Detect unused imports in Python AST."""
        issues: List[Issue] = []

        # Step A: Collect all referenced identifiers
        referenced_names: Set[str] = set()
        all_exports: Set[str] = set()

        # Find __all__ exports
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    all_exports.add(elt.value)

        referenced_names.update(all_exports)

        # Traverse non-import nodes to find all referenced names
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue

            if isinstance(node, ast.Name):
                referenced_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                # Also include attribute lookups (e.g. os.path)
                referenced_names.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Forward reference string annotations (e.g., 'MyModel')
                val = node.value.strip()
                if val.isidentifier():
                    referenced_names.add(val)

        # Allow __init__.py re-exports if it's an __init__.py package index file
        is_init_py = file_path.replace("\\", "/").endswith("/__init__.py") or file_path == "__init__.py"

        # Step B: Check imports
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound_name = alias.asname or alias.name.split(".")[0]
                    if is_init_py and alias.asname is None and not all_exports:
                        # In __init__.py, plain imports without explicit __all__ are often package exposures
                        continue

                    if bound_name not in referenced_names:
                        loc = Location(
                            path=file_path,
                            line=node.lineno,
                            col=node.col_offset + 1,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            end_col=getattr(node, "end_col_offset", None),
                        )
                        issues.append(
                            Issue(
                                issue_type=IssueType.ORPHANED_IMPORT,
                                location=loc,
                                symbol=bound_name,
                                message=f"Imported symbol '{bound_name}' is never used",
                                severity=Severity.WARNING,
                                details=f"Import statement: 'import {alias.name}{' as ' + alias.asname if alias.asname else ''}'",
                                fixable=True,
                            )
                        )

            elif isinstance(node, ast.ImportFrom):
                # Ignore wildcard imports
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound_name = alias.asname or alias.name
                    if is_init_py and not all_exports:
                        # In __init__.py without __all__, imports might be public re-exports
                        continue

                    if bound_name not in referenced_names:
                        loc = Location(
                            path=file_path,
                            line=node.lineno,
                            col=node.col_offset + 1,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            end_col=getattr(node, "end_col_offset", None),
                        )
                        mod = node.module or "." * (node.level or 1)
                        issues.append(
                            Issue(
                                issue_type=IssueType.ORPHANED_IMPORT,
                                location=loc,
                                symbol=bound_name,
                                message=f"Imported symbol '{bound_name}' from '{mod}' is never used",
                                severity=Severity.WARNING,
                                details=f"From import: 'from {mod} import {alias.name}'",
                                fixable=True,
                            )
                        )

        return issues

    def _find_unreachable_code(self, tree: ast.AST, file_path: str) -> List[Issue]:
        """Detect unreachable statements in control flow and dead branches."""
        issues: List[Issue] = []

        def inspect_statement_list(stmts: List[ast.stmt]) -> None:
            if not stmts:
                return

            for i, stmt in enumerate(stmts):
                is_term, term_desc = _is_terminal_statement(stmt)
                if is_term and i + 1 < len(stmts):
                    # All remaining statements are unreachable
                    next_stmt = stmts[i + 1]
                    last_stmt = stmts[-1]
                    loc = Location(
                        path=file_path,
                        line=next_stmt.lineno,
                        col=next_stmt.col_offset + 1,
                        end_line=getattr(last_stmt, "end_lineno", last_stmt.lineno),
                        end_col=getattr(last_stmt, "end_col_offset", None),
                    )
                    count = len(stmts) - (i + 1)
                    stmt_plural = "statement" if count == 1 else "statements"
                    issues.append(
                        Issue(
                            issue_type=IssueType.UNREACHABLE_CODE,
                            location=loc,
                            symbol="<unreachable>",
                            message=f"{count} {stmt_plural} after '{term_desc}' (line {stmt.lineno}) will never execute",
                            severity=Severity.WARNING,
                            details=f"Terminated by '{term_desc}' statement at line {stmt.lineno}",
                            fixable=False,
                        )
                    )
                    # Don't inspect subsequent dead statements for secondary unreachable issues
                    break

        # Walk AST and check all blocks
        for node in ast.walk(tree):
            # Check sequential statement lists
            if hasattr(node, "body") and isinstance(node.body, list):
                inspect_statement_list(node.body)
            if hasattr(node, "orelse") and isinstance(node.orelse, list):
                inspect_statement_list(node.orelse)
            if hasattr(node, "finalbody") and isinstance(node.finalbody, list):
                inspect_statement_list(node.finalbody)

            # Check dead branches: if False / if 0
            if isinstance(node, ast.If):
                if _is_constant_false(node.test) and node.body:
                    first_stmt = node.body[0]
                    last_stmt = node.body[-1]
                    loc = Location(
                        path=file_path,
                        line=first_stmt.lineno,
                        col=first_stmt.col_offset + 1,
                        end_line=getattr(last_stmt, "end_lineno", last_stmt.lineno),
                    )
                    issues.append(
                        Issue(
                            issue_type=IssueType.UNREACHABLE_CODE,
                            location=loc,
                            symbol="<dead-branch>",
                            message="Branch condition is statically False; block is never executed",
                            severity=Severity.WARNING,
                            details="if False / if 0 branch",
                            fixable=False,
                        )
                    )
                elif _is_constant_true(node.test) and node.orelse:
                    first_stmt = node.orelse[0]
                    last_stmt = node.orelse[-1]
                    loc = Location(
                        path=file_path,
                        line=first_stmt.lineno,
                        col=first_stmt.col_offset + 1,
                        end_line=getattr(last_stmt, "end_lineno", last_stmt.lineno),
                    )
                    issues.append(
                        Issue(
                            issue_type=IssueType.UNREACHABLE_CODE,
                            location=loc,
                            symbol="<dead-branch>",
                            message="Else branch condition is unreachable because if test is statically True",
                            severity=Severity.WARNING,
                            details="else branch with statically True if condition",
                            fixable=False,
                        )
                    )

            # Check dead while loops: while False
            if isinstance(node, ast.While):
                if _is_constant_false(node.test) and node.body:
                    first_stmt = node.body[0]
                    last_stmt = node.body[-1]
                    loc = Location(
                        path=file_path,
                        line=first_stmt.lineno,
                        col=first_stmt.col_offset + 1,
                        end_line=getattr(last_stmt, "end_lineno", last_stmt.lineno),
                    )
                    issues.append(
                        Issue(
                            issue_type=IssueType.UNREACHABLE_CODE,
                            location=loc,
                            symbol="<dead-loop>",
                            message="Loop condition is statically False; loop body is never executed",
                            severity=Severity.WARNING,
                            details="while False loop",
                            fixable=False,
                        )
                    )

        return issues

    def _find_unused_functions(
        self,
        tree: ast.Module,
        file_path: str,
        context: Optional[ProjectContext] = None,
        ignore_names: Optional[Set[str]] = None,
        include_public_functions: bool = False,
    ) -> List[Issue]:
        """Detect unused function and method definitions."""
        issues: List[Issue] = []
        ignored = ignore_names or set()

        # Find all export names in __all__
        all_exports: Set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    all_exports.add(elt.value)

        # Collect references across entire file
        file_references: Set[str] = set(all_exports)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                file_references.add(node.id)
            elif isinstance(node, ast.Attribute):
                file_references.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.isidentifier():
                    file_references.add(node.value)

        def is_decorated_with_framework_hook(fn_node: ast.AST) -> bool:
            for decorator in getattr(fn_node, "decorator_list", []):
                dec_name = ""
                if isinstance(decorator, ast.Name):
                    dec_name = decorator.id
                elif isinstance(decorator, ast.Attribute):
                    dec_name = decorator.attr
                elif isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Name):
                        dec_name = decorator.func.id
                    elif isinstance(decorator.func, ast.Attribute):
                        dec_name = decorator.func.attr

                dec_name_lower = dec_name.lower()
                for hook in COMMON_FRAMEWORK_DECORATORS:
                    if hook in dec_name_lower:
                        return True
            return False

        # Check function definitions
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            fn_name = node.name

            # Skip dunder methods
            if fn_name.startswith("__") and fn_name.endswith("__"):
                continue

            # Skip test functions and explicitly ignored names
            if fn_name.startswith("test_") or fn_name in ignored:
                continue

            # Skip framework decorated functions
            if is_decorated_with_framework_hook(node):
                continue

            # Collect internal nodes of this function
            internal_nodes = set(ast.walk(node))

            # Count occurrences of fn_name OUTSIDE this function definition
            external_refs = 0
            for ref_node in ast.walk(tree):
                if ref_node in internal_nodes:
                    continue
                if isinstance(ref_node, ast.Name) and ref_node.id == fn_name:
                    external_refs += 1
                elif isinstance(ref_node, ast.Attribute) and ref_node.attr == fn_name:
                    external_refs += 1

            is_used_in_file = external_refs > 0

            # Decide whether to flag:
            should_flag = False
            flag_reason = ""

            # Check if private function (starts with _)
            is_private = fn_name.startswith("_")

            if is_private:
                # Private functions should be referenced in the same file
                if not is_used_in_file:
                    should_flag = True
                    flag_reason = f"Private function '{fn_name}' is never called or referenced within '{file_path}'"
            else:
                # Public function
                if fn_name in all_exports:
                    # Explicitly exported via __all__
                    continue

                if context is not None:
                    # Multi-file project mode: check if referenced in ANY scanned file
                    is_used_in_project = context.is_symbol_referenced(fn_name, exclude_file=file_path)
                    if not is_used_in_file and not is_used_in_project:
                        should_flag = True
                        flag_reason = f"Function '{fn_name}' is never referenced across the project"
                elif include_public_functions:
                    if not is_used_in_file:
                        should_flag = True
                        flag_reason = f"Public function '{fn_name}' is not called within file (flagged with --include-public-functions)"

            if should_flag:
                loc = Location(
                    path=file_path,
                    line=node.lineno,
                    col=node.col_offset + 1,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    end_col=getattr(node, "end_col_offset", None),
                )
                issues.append(
                    Issue(
                        issue_type=IssueType.UNUSED_FUNCTION,
                        location=loc,
                        symbol=fn_name,
                        message=flag_reason or f"Function '{fn_name}' appears to be unused dead code",
                        severity=Severity.WARNING,
                        details=f"Defined at line {node.lineno}",
                        fixable=False,
                    )
                )

        return issues
