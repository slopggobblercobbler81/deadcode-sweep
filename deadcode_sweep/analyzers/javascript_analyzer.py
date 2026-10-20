"""Static analyzer for JavaScript and TypeScript codebases."""

import re
from typing import Dict, List, Optional, Set, Tuple

from deadcode_sweep.analyzers.base import BaseAnalyzer
from deadcode_sweep.models import (
    AnalysisResult,
    Issue,
    IssueType,
    Location,
    ProjectContext,
    Severity,
)

JS_COMMON_IGNORED = {
    "render",
    "constructor",
    "componentDidMount",
    "componentWillUnmount",
    "componentDidUpdate",
    "main",
    "handler",
    "getInitialProps",
    "getServerSideProps",
    "getStaticProps",
    "test",
    "it",
    "describe",
    "beforeEach",
    "afterEach",
    "beforeAll",
    "afterAll",
}


def _strip_comments_and_strings(source: str) -> Tuple[str, str]:
    """
    Produce two stripped versions preserving exact line and column offsets:
    1. code_no_comments: comments replaced with spaces/newlines, strings intact.
    2. code_structure_only: both comments and strings replaced with spaces/newlines.
    """
    chars_no_comments = list(source)
    chars_structure = list(source)
    n = len(source)
    i = 0

    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        # Single line comment //
        if c == "/" and nxt == "/":
            start = i
            while i < n and source[i] != "\n":
                i += 1
            for j in range(start, i):
                chars_no_comments[j] = " "
                chars_structure[j] = " "
            continue

        # Multi-line comment /* */
        if c == "/" and nxt == "*":
            start = i
            i += 2
            while i < n - 1 and not (source[i] == "*" and source[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            for j in range(start, i):
                if source[j] != "\n":
                    chars_no_comments[j] = " "
                    chars_structure[j] = " "
            continue

        # String literals: ', ", `
        if c in ("'", '"', "`"):
            quote = c
            start = i
            i += 1
            while i < n:
                if source[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if source[i] == quote:
                    i += 1
                    break
                i += 1
            # In structure string, blank out string content except newlines
            for j in range(start, min(i, n)):
                if source[j] != "\n":
                    chars_structure[j] = " "
            continue

        i += 1

    return "".join(chars_no_comments), "".join(chars_structure)


class JavaScriptAnalyzer(BaseAnalyzer):
    """Static analyzer for JavaScript and TypeScript code."""

    @property
    def name(self) -> str:
        return "javascript"

    @property
    def supported_extensions(self) -> Tuple[str, ...]:
        return (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

    def collect_symbols(
        self,
        code: str,
        file_path: str,
        context: ProjectContext,
    ) -> None:
        """Pass 1: Collect definitions and symbol usages for project-wide analysis."""
        clean_code, struct_code = _strip_comments_and_strings(code)

        # Record exported functions
        export_fn_pattern = re.compile(
            r"export\s+(?:default\s+)?(?:async\s+)?function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)"
        )
        for m in export_fn_pattern.finditer(clean_code):
            fn_name = m.group(1)
            context.exported_symbols.add(fn_name)

        export_const_fn_pattern = re.compile(
            r"export\s+const\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z_$][a-zA-Z0-9_$]*)\s*=>"
        )
        for m in export_const_fn_pattern.finditer(clean_code):
            fn_name = m.group(1)
            context.exported_symbols.add(fn_name)

        # Collect all identifiers referenced outside strings/comments
        id_pattern = re.compile(r"\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b")
        for m in id_pattern.finditer(struct_code):
            context.register_reference(m.group(1), file_path)

    def analyze_code(
        self,
        code: str,
        file_path: str,
        context: Optional[ProjectContext] = None,
        ignore_names: Optional[Set[str]] = None,
        include_public_functions: bool = False,
    ) -> AnalysisResult:
        """Analyze JavaScript/TypeScript source code for dead code issues."""
        lines = code.splitlines()
        lines_scanned = len(lines)
        ignored = (ignore_names or set()) | JS_COMMON_IGNORED

        clean_code, struct_code = _strip_comments_and_strings(code)
        issues: List[Issue] = []

        # 1. Orphaned Imports
        issues.extend(self._find_orphaned_imports(code, clean_code, struct_code, file_path))

        # 2. Unreachable Code
        issues.extend(self._find_unreachable_code(code, struct_code, file_path))

        # 3. Unused Functions
        issues.extend(
            self._find_unused_functions(
                code,
                clean_code,
                struct_code,
                file_path,
                context=context,
                ignore_names=ignored,
                include_public_functions=include_public_functions,
            )
        )

        issues.sort(key=lambda x: (x.location.line, x.location.col))
        return AnalysisResult(
            file_path=file_path,
            issues=issues,
            lines_scanned=lines_scanned,
        )

    def _line_and_col_of_offset(self, source: str, offset: int) -> Tuple[int, int]:
        prefix = source[:offset]
        line = prefix.count("\n") + 1
        last_nl = prefix.rfind("\n")
        col = offset + 1 if last_nl == -1 else offset - last_nl
        return line, col

    def _find_orphaned_imports(
        self, source: str, clean_code: str, struct_code: str, file_path: str
    ) -> List[Issue]:
        issues: List[Issue] = []

        # Store import definitions: symbol -> (offset, full_import_line, module_name)
        imports: Dict[str, Tuple[int, str, str]] = {}

        # 1. ES6 import statements:
        # e.g.: import foo from 'bar';
        #       import { a, b as c } from 'bar';
        #       import * as all from 'bar';
        es6_import_regex = re.compile(
            r"import\s+(?:type\s+)?([^{;'\"]*?)\s*(?:from\s*['\"]([^'\"]+)['\"])?;",
            re.MULTILINE,
        )

        # Match ES6 imports more precisely
        full_es6_regex = re.compile(
            r"import\s+(?:type\s+)?(?:([a-zA-Z_$][a-zA-Z0-9_$]*)\s*,?\s*)?"
            r"(?:\*\s*as\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*,?\s*)?"
            r"(?:\{([^}]*)\})?\s*from\s*['\"]([^'\"]+)['\"]",
            re.MULTILINE,
        )

        import_spans: List[Tuple[int, int]] = []

        for m in full_es6_regex.finditer(source):
            def_default = m.group(1)
            star_alias = m.group(2)
            named_block = m.group(3)
            module_name = m.group(4)
            offset = m.start()
            import_spans.append((m.start(), m.end()))

            if def_default:
                imports[def_default] = (offset, m.group(0), module_name)

            if star_alias:
                imports[star_alias] = (offset, m.group(0), module_name)

            if named_block:
                for part in named_block.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if " as " in part:
                        _, alias = part.split(" as ", 1)
                        bound_name = alias.strip()
                    else:
                        bound_name = part.strip()
                    if bound_name:
                        imports[bound_name] = (offset, m.group(0), module_name)

        # 2. CommonJS require statements:
        cjs_default_regex = re.compile(
            r"(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            re.MULTILINE,
        )
        for m in cjs_default_regex.finditer(source):
            bound_name = m.group(1)
            module_name = m.group(2)
            imports[bound_name] = (m.start(), m.group(0), module_name)
            import_spans.append((m.start(), m.end()))

        cjs_destruct_regex = re.compile(
            r"(?:const|let|var)\s+\{\s*([^}]+)\s*\}\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            re.MULTILINE,
        )
        for m in cjs_destruct_regex.finditer(source):
            named_block = m.group(1)
            module_name = m.group(2)
            offset = m.start()
            import_spans.append((m.start(), m.end()))
            for part in named_block.split(","):
                part = part.strip()
                if not part:
                    continue
                if ":" in part:
                    _, alias = part.split(":", 1)
                    bound_name = alias.strip()
                else:
                    bound_name = part.strip()
                if bound_name:
                    imports[bound_name] = (offset, m.group(0), module_name)

        # Blank out all import statements in struct_code (which has comments & strings stripped)
        code_without_imports = list(struct_code)
        for start, end in import_spans:
            for i in range(start, min(end, len(code_without_imports))):
                if code_without_imports[i] != "\n":
                    code_without_imports[i] = " "

        rest_code = "".join(code_without_imports)

        for sym, (offset, full_stmt, mod) in imports.items():
            # Check if sym is used as an identifier token elsewhere
            pattern = re.compile(rf"\b{re.escape(sym)}\b")
            if not pattern.search(rest_code):
                line, col = self._line_and_col_of_offset(source, offset)
                loc = Location(path=file_path, line=line, col=col)
                issues.append(
                    Issue(
                        issue_type=IssueType.ORPHANED_IMPORT,
                        location=loc,
                        symbol=sym,
                        message=f"Imported symbol '{sym}' from '{mod}' is never used",
                        severity=Severity.WARNING,
                        details=f"Import declaration: {full_stmt.strip()}",
                        fixable=True,
                    )
                )

        return issues

    def _find_unreachable_code(
        self, source: str, struct_code: str, file_path: str
    ) -> List[Issue]:
        issues: List[Issue] = []

        # 1. Dead branches: if (false), if (0), while (false), while (0)
        dead_if_regex = re.compile(r"\bif\s*\(\s*(?:false|0|!true)\s*\)\s*\{", re.MULTILINE)
        for m in dead_if_regex.finditer(struct_code):
            line, col = self._line_and_col_of_offset(source, m.start())
            loc = Location(path=file_path, line=line, col=col)
            issues.append(
                Issue(
                    issue_type=IssueType.UNREACHABLE_CODE,
                    location=loc,
                    symbol="<dead-branch>",
                    message="Branch condition is statically false; branch block is unreachable",
                    severity=Severity.WARNING,
                    details="if (false) or if (0) branch",
                    fixable=False,
                )
            )

        dead_while_regex = re.compile(r"\bwhile\s*\(\s*(?:false|0)\s*\)\s*\{", re.MULTILINE)
        for m in dead_while_regex.finditer(struct_code):
            line, col = self._line_and_col_of_offset(source, m.start())
            loc = Location(path=file_path, line=line, col=col)
            issues.append(
                Issue(
                    issue_type=IssueType.UNREACHABLE_CODE,
                    location=loc,
                    symbol="<dead-loop>",
                    message="Loop condition is statically false; loop block is unreachable",
                    severity=Severity.WARNING,
                    details="while (false) or while (0) loop",
                    fixable=False,
                )
            )

        # 2. Sequential unreachable code inside blocks after return, throw, break, continue
        # Find terminal statements and check what follows before the block's closing brace '}'
        terminal_regex = re.compile(
            r"\b(return|throw|break|continue)\b([^;{}]*);", re.MULTILINE
        )
        for m in terminal_regex.finditer(struct_code):
            term_keyword = m.group(1)
            term_end = m.end()

            # Scan forward from term_end
            idx = term_end
            has_dead_code = False
            dead_start = -1

            while idx < len(struct_code):
                ch = struct_code[idx]
                if ch in (" ", "\t", "\r", "\n"):
                    idx += 1
                    continue
                if ch == "}":
                    # Reached end of block without dead code
                    break
                elif ch == "{":
                    # Sub-block starts; this is unreachable
                    has_dead_code = True
                    dead_start = idx
                    break
                else:
                    # Statement characters!
                    has_dead_code = True
                    dead_start = idx
                    break

            if has_dead_code and dead_start != -1:
                line, col = self._line_and_col_of_offset(source, dead_start)
                term_line, _ = self._line_and_col_of_offset(source, m.start())
                loc = Location(path=file_path, line=line, col=col)
                issues.append(
                    Issue(
                        issue_type=IssueType.UNREACHABLE_CODE,
                        location=loc,
                        symbol="<unreachable>",
                        message=f"Code following '{term_keyword}' (line {term_line}) is unreachable",
                        severity=Severity.WARNING,
                        details=f"Terminated by '{term_keyword}' on line {term_line}",
                        fixable=False,
                    )
                )

        return issues

    def _find_unused_functions(
        self,
        source: str,
        clean_code: str,
        struct_code: str,
        file_path: str,
        context: Optional[ProjectContext] = None,
        ignore_names: Optional[Set[str]] = None,
        include_public_functions: bool = False,
    ) -> List[Issue]:
        issues: List[Issue] = []
        ignored = ignore_names or set()

        # Find exported functions
        exported_names: Set[str] = set()
        export_decl_regex = re.compile(
            r"export\s+(?:default\s+)?(?:async\s+)?(?:function|const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)"
        )
        for m in export_decl_regex.finditer(struct_code):
            exported_names.add(m.group(1))

        # Check export { a, b }
        export_named_regex = re.compile(r"export\s+\{([^}]+)\}")
        for m in export_named_regex.finditer(struct_code):
            for part in m.group(1).split(","):
                part = part.strip()
                if " as " in part:
                    orig, _ = part.split(" as ", 1)
                    exported_names.add(orig.strip())
                elif part:
                    exported_names.add(part)

        # Also module.exports = ...
        if "module.exports" in clean_code or "exports." in clean_code:
            # CommonJS exports
            cjs_exp_regex = re.compile(r"exports\.([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=")
            for m in cjs_exp_regex.finditer(clean_code):
                exported_names.add(m.group(1))

        # Find function definitions:
        # 1. function name(...) {
        fn_decl_regex = re.compile(
            r"(?<!export\s)(?<!export\sdefault\s)\b(?:async\s+)?function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\("
        )
        # 2. const name = (...) => { or const name = function(...) {
        fn_expr_regex = re.compile(
            r"(?<!export\s)\b(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z_$][a-zA-Z0-9_$]*)\s*=>"
        )
        fn_anon_regex = re.compile(
            r"(?<!export\s)\b(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s+)?function\b"
        )

        candidates: Dict[str, int] = {}
        for m in fn_decl_regex.finditer(struct_code):
            fn_name = m.group(1)
            if fn_name not in exported_names:
                candidates[fn_name] = m.start()

        for m in fn_expr_regex.finditer(struct_code):
            fn_name = m.group(1)
            if fn_name not in exported_names:
                candidates[fn_name] = m.start()

        for m in fn_anon_regex.finditer(struct_code):
            fn_name = m.group(1)
            if fn_name not in exported_names:
                candidates[fn_name] = m.start()

        for fn_name, offset in candidates.items():
            if fn_name in ignored:
                continue

            # Check usages of fn_name as an identifier
            id_regex = re.compile(rf"\b{re.escape(fn_name)}\b")
            matches = list(id_regex.finditer(clean_code))

            # The definition itself is 1 match
            is_used_in_file = len(matches) > 1
            is_private = fn_name.startswith("_")

            should_flag = False
            flag_reason = ""

            if is_private:
                if not is_used_in_file:
                    should_flag = True
                    flag_reason = f"Private function '{fn_name}' is never called within '{file_path}'"
            elif include_public_functions:
                if not is_used_in_file:
                    should_flag = True
                    flag_reason = f"Function '{fn_name}' is unexported and never called within '{file_path}'"
            elif context is not None:
                # Multi-file analysis
                total_refs = len(context.referenced_symbols.get(fn_name, set()))
                if not is_used_in_file and total_refs == 0:
                    should_flag = True
                    flag_reason = f"Unexported function '{fn_name}' is never called across the codebase"
                elif not is_used_in_file and not context.is_symbol_referenced(fn_name, exclude_file=file_path):
                    should_flag = True
                    flag_reason = f"Unexported function '{fn_name}' is not called within this file or referenced by others"
            else:
                # Single-file mode without flags: flag unexported functions that are never called
                if not is_used_in_file:
                    should_flag = True
                    flag_reason = f"Function '{fn_name}' is defined but never called or exported in this file"

            if should_flag:
                line, col = self._line_and_col_of_offset(source, offset)
                loc = Location(path=file_path, line=line, col=col)
                issues.append(
                    Issue(
                        issue_type=IssueType.UNUSED_FUNCTION,
                        location=loc,
                        symbol=fn_name,
                        message=flag_reason,
                        severity=Severity.WARNING,
                        details=f"Defined at line {line}",
                        fixable=False,
                    )
                )

        return issues
