"""Output formatters for deadcode-sweep reports."""

import csv
import io
import json
from typing import List

from deadcode_sweep.models import IssueType, Report, Severity

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"


class Formatter:
    """Format deadcode analysis reports in various output formats."""

    @staticmethod
    def format(
        report: Report,
        fmt: str = "text",
        no_color: bool = False,
        min_severity: str = "warning",
    ) -> str:
        fmt = fmt.lower()
        min_sev_obj = Severity(min_severity)

        # Filter issues by minimum severity
        filtered_results = []
        for res in report.results:
            filtered_issues = [
                i for i in res.issues if i.severity.level >= min_sev_obj.level
            ]
            if filtered_issues or res.parse_error:
                # Keep copy with filtered issues
                res_copy = type(res)(
                    file_path=res.file_path,
                    issues=filtered_issues,
                    lines_scanned=res.lines_scanned,
                    parse_error=res.parse_error,
                )
                filtered_results.append(res_copy)
            else:
                res_copy = type(res)(
                    file_path=res.file_path,
                    issues=[],
                    lines_scanned=res.lines_scanned,
                )
                filtered_results.append(res_copy)

        report_copy = Report(
            results=filtered_results,
            total_files=report.total_files,
            total_lines=report.total_lines,
            duration_seconds=report.duration_seconds,
            fixed_count=report.fixed_count,
        )

        if fmt == "json":
            return Formatter._format_json(report_copy)
        elif fmt == "csv":
            return Formatter._format_csv(report_copy)
        elif fmt == "github":
            return Formatter._format_github(report_copy)
        elif fmt == "summary":
            return Formatter._format_summary(report_copy, no_color=no_color)
        else:
            return Formatter._format_text(report_copy, no_color=no_color)

    @staticmethod
    def _format_json(report: Report) -> str:
        return json.dumps(report.to_dict(), indent=2)

    @staticmethod
    def _format_csv(report: Report) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["file", "line", "col", "end_line", "end_col", "type", "severity", "symbol", "message"]
        )
        for issue in report.all_issues:
            writer.writerow(
                [
                    issue.location.path,
                    issue.location.line,
                    issue.location.col,
                    issue.location.end_line or "",
                    issue.location.end_col or "",
                    issue.issue_type.value,
                    issue.severity.value,
                    issue.symbol,
                    issue.message,
                ]
            )
        return output.getvalue()

    @staticmethod
    def _format_github(report: Report) -> str:
        lines: List[str] = []
        for issue in report.all_issues:
            level = "error" if issue.severity == Severity.ERROR else "warning"
            file_arg = issue.location.path
            line_arg = issue.location.line
            col_arg = issue.location.col
            msg = f"[{issue.issue_type.value}] {issue.message}"
            lines.append(f"::{level} file={file_arg},line={line_arg},col={col_arg}::{msg}")
        return "\n".join(lines)

    @staticmethod
    def _format_text(report: Report, no_color: bool = False) -> str:
        def c(color_str: str, text: str) -> str:
            return text if no_color else f"{color_str}{text}{RESET}"

        out: List[str] = []
        out.append(c(BOLD + CYAN, ">> deadcode-sweep") + c(DIM, " - Static Dead Code Analyzer"))
        out.append("")

        files_with_issues = [r for r in report.results if r.issues or r.parse_error]

        if not files_with_issues:
            out.append(c(GREEN + BOLD, "[+] No dead code detected! Clean codebase."))
        else:
            for res in files_with_issues:
                out.append(c(BOLD, f"  {res.file_path}"))
                if res.parse_error:
                    out.append(c(RED, f"    ERROR: {res.parse_error}"))
                    continue

                for issue in res.issues:
                    loc = f"{issue.location.line}:{issue.location.col}"
                    if issue.severity == Severity.ERROR:
                        tag = c(RED + BOLD, "[ERROR]")
                    elif issue.severity == Severity.WARNING:
                        tag = c(YELLOW + BOLD, "[WARN] ")
                    else:
                        tag = c(DIM, "[INFO] ")

                    type_tag = c(MAGENTA, f"{issue.issue_type.value:<16}")
                    out.append(f"    {c(DIM, loc):<12} {tag} {type_tag} {issue.message}")

                out.append("")

        # Summary box
        counts = report.issues_by_type()
        out.append(c(DIM, "-" * 60))
        stats = (
            f"Files scanned: {report.total_files} | "
            f"Lines: {report.total_lines} | "
            f"Issues: {report.total_issues} | "
            f"Duration: {report.duration_seconds:.2f}s"
        )
        out.append(c(BOLD, stats))

        breakdown = (
            f"Orphaned imports: {counts.get(IssueType.ORPHANED_IMPORT.value, 0)} | "
            f"Unused functions: {counts.get(IssueType.UNUSED_FUNCTION.value, 0)} | "
            f"Unreachable code: {counts.get(IssueType.UNREACHABLE_CODE.value, 0)}"
        )
        out.append(c(DIM, breakdown))

        if report.fixed_count > 0:
            out.append(c(GREEN + BOLD, f"Fixed: {report.fixed_count} orphaned import(s) removed."))

        out.append(c(DIM, "-" * 60))
        return "\n".join(out)

    @staticmethod
    def _format_summary(report: Report, no_color: bool = False) -> str:
        def c(color_str: str, text: str) -> str:
            return text if no_color else f"{color_str}{text}{RESET}"

        header = f"{'File':<40} {'Lines':>6} {'Imports':>8} {'Funcs':>8} {'Unreach':>8}"
        sep = "-" * len(header)
        out: List[str] = [c(BOLD, header), sep]

        for res in report.results:
            n_imp = sum(1 for i in res.issues if i.issue_type == IssueType.ORPHANED_IMPORT)
            n_fn = sum(1 for i in res.issues if i.issue_type == IssueType.UNUSED_FUNCTION)
            n_un = sum(1 for i in res.issues if i.issue_type == IssueType.UNREACHABLE_CODE)
            path_display = res.file_path if len(res.file_path) <= 40 else "..." + res.file_path[-37:]
            row = f"{path_display:<40} {res.lines_scanned:>6} {n_imp:>8} {n_fn:>8} {n_un:>8}"
            out.append(row)

        out.append(sep)
        counts = report.issues_by_type()
        tot_row = (
            f"{'TOTAL':<40} {report.total_lines:>6} "
            f"{counts.get(IssueType.ORPHANED_IMPORT.value, 0):>8} "
            f"{counts.get(IssueType.UNUSED_FUNCTION.value, 0):>8} "
            f"{counts.get(IssueType.UNREACHABLE_CODE.value, 0):>8}"
        )
        out.append(c(BOLD, tot_row))
        return "\n".join(out)
