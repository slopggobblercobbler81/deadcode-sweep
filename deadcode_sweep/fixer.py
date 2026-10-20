"""Auto-fixer for removing orphaned imports in Python and JavaScript."""

import ast
import re
from pathlib import Path
from typing import List, Set, Tuple

from deadcode_sweep.models import Issue, IssueType


class Fixer:
    """Safely fixes auto-fixable issues like orphaned imports."""

    @staticmethod
    def fix_file(file_path: str, issues: List[Issue]) -> int:
        """
        Fix auto-fixable issues in the given file.
        Returns the number of fixes applied.
        """
        fixable_issues = [
            i for i in issues if i.fixable and i.issue_type == IssueType.ORPHANED_IMPORT
        ]
        if not fixable_issues:
            return 0

        path = Path(file_path)
        if not path.exists():
            return 0

        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return 0

        ext = path.suffix.lower()
        if ext in (".py", ".pyw", ".pyi"):
            fixed_count, new_content = Fixer._fix_python_imports(content, fixable_issues)
        elif ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
            fixed_count, new_content = Fixer._fix_javascript_imports(content, fixable_issues)
        else:
            return 0

        if fixed_count > 0 and new_content != content:
            path.write_text(new_content, encoding="utf-8")

        return fixed_count

    @staticmethod
    def _fix_python_imports(content: str, issues: List[Issue]) -> Tuple[int, str]:
        """Remove orphaned imports in Python files."""
        unused_symbols = {issue.symbol for issue in issues}
        if not unused_symbols:
            return 0, content

        lines = content.splitlines(keepends=True)
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return 0, content

        # Identify lines to remove or modify
        lines_to_remove: Set[int] = set()
        replacements: List[Tuple[int, str]] = []
        fixes_applied = 0

        for node in tree.body:
            if isinstance(node, ast.Import):
                unused_in_node = []
                used_in_node = []
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    if bound in unused_symbols:
                        unused_in_node.append(alias)
                    else:
                        used_in_node.append(alias)

                if unused_in_node:
                    fixes_applied += len(unused_in_node)
                    if not used_in_node:
                        # Remove entire statement (1-based lineno)
                        start = node.lineno - 1
                        end = getattr(node, "end_lineno", node.lineno)
                        for idx in range(start, end):
                            lines_to_remove.add(idx)
                    else:
                        # Rebuild import with only used aliases
                        aliases_str = ", ".join(
                            f"{a.name} as {a.asname}" if a.asname else a.name
                            for a in used_in_node
                        )
                        orig_line = lines[node.lineno - 1]
                        indent = orig_line[: len(orig_line) - len(orig_line.lstrip())]
                        newline = f"{indent}import {aliases_str}\n"
                        replacements.append((node.lineno - 1, newline))

            elif isinstance(node, ast.ImportFrom):
                unused_in_node = []
                used_in_node = []
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if bound in unused_symbols:
                        unused_in_node.append(alias)
                    else:
                        used_in_node.append(alias)

                if unused_in_node:
                    fixes_applied += len(unused_in_node)
                    if not used_in_node:
                        # Remove entire statement
                        start = node.lineno - 1
                        end = getattr(node, "end_lineno", node.lineno)
                        for idx in range(start, end):
                            lines_to_remove.add(idx)
                    else:
                        # Rebuild from-import
                        mod = ("." * (node.level or 0)) + (node.module or "")
                        aliases_str = ", ".join(
                            f"{a.name} as {a.asname}" if a.asname else a.name
                            for a in used_in_node
                        )
                        orig_line = lines[node.lineno - 1]
                        indent = orig_line[: len(orig_line) - len(orig_line.lstrip())]
                        newline = f"{indent}from {mod} import {aliases_str}\n"
                        replacements.append((node.lineno - 1, newline))

        # Apply replacements
        for line_idx, new_line in replacements:
            lines[line_idx] = new_line

        # Reconstruct output excluding lines_to_remove
        output_lines = [line for idx, line in enumerate(lines) if idx not in lines_to_remove]
        return fixes_applied, "".join(output_lines)

    @staticmethod
    def _fix_javascript_imports(content: str, issues: List[Issue]) -> Tuple[int, str]:
        """Remove orphaned imports in JavaScript files."""
        unused_symbols = {issue.symbol for issue in issues}
        if not unused_symbols:
            return 0, content

        lines = content.splitlines(keepends=True)
        lines_to_remove: Set[int] = set()
        fixes_applied = 0

        # Process line by line
        for idx, line in enumerate(lines):
            # Check for simple single-import line:
            # import foo from 'bar'; or const foo = require('bar');
            for sym in list(unused_symbols):
                # import sym from '...';
                single_es6 = re.compile(
                    rf"^\s*import\s+{re.escape(sym)}\s+from\s+['\"][^'\"]+['\"];?\s*$"
                )
                # const sym = require('...');
                single_cjs = re.compile(
                    rf"^\s*(?:const|let|var)\s+{re.escape(sym)}\s*=\s*require\s*\([^)]+\);?\s*$"
                )
                if single_es6.match(line) or single_cjs.match(line):
                    lines_to_remove.add(idx)
                    fixes_applied += 1
                    unused_symbols.remove(sym)
                    break

                # import { sym } from '...';
                named_single_es6 = re.compile(
                    rf"^\s*import\s*\{{\s*{re.escape(sym)}\s*\}}\s*from\s+['\"][^'\"]+['\"];?\s*$"
                )
                if named_single_es6.match(line):
                    lines_to_remove.add(idx)
                    fixes_applied += 1
                    unused_symbols.remove(sym)
                    break

        output_lines = [line for idx, line in enumerate(lines) if idx not in lines_to_remove]
        return fixes_applied, "".join(output_lines)
