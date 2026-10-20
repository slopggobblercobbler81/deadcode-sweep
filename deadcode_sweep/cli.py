"""Command line interface for deadcode-sweep."""

import argparse
import sys
from typing import List, Optional

from deadcode_sweep import __version__
from deadcode_sweep.formatter import Formatter
from deadcode_sweep.scanner import Scanner


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deadcode-sweep",
        description="Fast static analyzer for Python and JavaScript codebases to detect unused functions, unreachable code, and orphaned imports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  deadcode-sweep .
  deadcode-sweep src/ --check
  deadcode-sweep . --lang python --fix
  deadcode-sweep . --format json -o report.json
  deadcode-sweep app/ --format github
        """,
    )

    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Target files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "--lang",
        choices=["all", "python", "javascript", "py", "js", "ts"],
        default="all",
        help="Filter languages to scan (default: all)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with returncode 1 if any dead code issues are found (ideal for CI)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically remove orphaned imports in-place",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "github", "summary"],
        default="text",
        help="Output report format (default: text)",
    )
    parser.add_argument(
        "--min-severity",
        choices=["info", "warning", "error"],
        default="warning",
        help="Minimum issue severity level to report (default: warning)",
    )
    parser.add_argument(
        "--ignore-dirs",
        type=str,
        default="",
        help="Comma-separated directory names to ignore during scanning",
    )
    parser.add_argument(
        "--ignore-names",
        type=str,
        default="",
        help="Comma-separated function or symbol names to ignore",
    )
    parser.add_argument(
        "--include-public-functions",
        action="store_true",
        help="Flag unreferenced public functions even in single-file checks",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Write report output to specified file path",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color codes in console output",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    parsed = parse_args(args)

    ignore_dirs = {d.strip() for d in parsed.ignore_dirs.split(",") if d.strip()}
    ignore_names = {n.strip() for n in parsed.ignore_names.split(",") if n.strip()}

    scanner = Scanner(
        lang=parsed.lang,
        ignore_dirs=ignore_dirs,
        ignore_names=ignore_names,
        include_public_functions=parsed.include_public_functions,
        fix=parsed.fix,
    )

    report = scanner.scan(parsed.paths)

    output = Formatter.format(
        report=report,
        fmt=parsed.format,
        no_color=parsed.no_color,
        min_severity=parsed.min_severity,
    )

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")
    else:
        print(output)

    if parsed.check and (report.total_issues > 0 or report.has_errors()):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
