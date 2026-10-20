"""Data models for deadcode-sweep."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class IssueType(str, Enum):
    ORPHANED_IMPORT = "orphaned_import"
    UNUSED_FUNCTION = "unused_function"
    UNREACHABLE_CODE = "unreachable_code"

    def __str__(self) -> str:
        return self.value


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    def __str__(self) -> str:
        return self.value

    @property
    def level(self) -> int:
        levels = {"info": 0, "warning": 1, "error": 2}
        return levels.get(self.value, 1)


@dataclass
class Location:
    path: str
    line: int
    col: int = 1
    end_line: Optional[int] = None
    end_col: Optional[int] = None

    def __str__(self) -> str:
        if self.end_line and self.end_line != self.line:
            return f"{self.path}:{self.line}:{self.col}-{self.end_line}:{self.end_col or ''}"
        return f"{self.path}:{self.line}:{self.col}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }


@dataclass
class Issue:
    issue_type: IssueType
    location: Location
    symbol: str
    message: str
    severity: Severity = Severity.WARNING
    details: Optional[str] = None
    fixable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.issue_type.value,
            "symbol": self.symbol,
            "message": self.message,
            "severity": self.severity.value,
            "location": self.location.to_dict(),
            "details": self.details,
            "fixable": self.fixable,
        }


@dataclass
class AnalysisResult:
    file_path: str
    issues: List[Issue] = field(default_factory=list)
    lines_scanned: int = 0
    parse_error: Optional[str] = None

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "lines_scanned": self.lines_scanned,
            "parse_error": self.parse_error,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class ProjectContext:
    """Project-wide cross-file reference and declaration tracking."""
    # Maps symbol name to set of file paths where it is referenced
    referenced_symbols: Dict[str, Set[str]] = field(default_factory=dict)
    # Maps (file_path, symbol_name) to Location where function is defined
    defined_functions: Dict[tuple, Location] = field(default_factory=dict)
    # Set of public/exported symbols
    exported_symbols: Set[str] = field(default_factory=set)

    def register_reference(self, symbol: str, file_path: str) -> None:
        if symbol not in self.referenced_symbols:
            self.referenced_symbols[symbol] = set()
        self.referenced_symbols[symbol].add(file_path)

    def register_function(self, symbol: str, file_path: str, location: Location) -> None:
        self.defined_functions[(file_path, symbol)] = location

    def is_symbol_referenced(self, symbol: str, exclude_file: Optional[str] = None) -> bool:
        refs = self.referenced_symbols.get(symbol, set())
        if exclude_file is None:
            return len(refs) > 0
        return any(f != exclude_file for f in refs)


@dataclass
class Report:
    results: List[AnalysisResult] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    duration_seconds: float = 0.0
    fixed_count: int = 0

    @property
    def all_issues(self) -> List[Issue]:
        issues = []
        for res in self.results:
            issues.extend(res.issues)
        return issues

    @property
    def total_issues(self) -> int:
        return sum(res.issue_count for res in self.results)

    def issues_by_type(self) -> Dict[str, int]:
        counts = {
            IssueType.ORPHANED_IMPORT.value: 0,
            IssueType.UNUSED_FUNCTION.value: 0,
            IssueType.UNREACHABLE_CODE.value: 0,
        }
        for issue in self.all_issues:
            counts[issue.issue_type.value] = counts.get(issue.issue_type.value, 0) + 1
        return counts

    def has_errors(self) -> bool:
        return any(
            issue.severity == Severity.ERROR for issue in self.all_issues
        ) or any(res.parse_error is not None for res in self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "total_files": self.total_files,
                "total_lines": self.total_lines,
                "total_issues": self.total_issues,
                "duration_seconds": round(self.duration_seconds, 4),
                "fixed_count": self.fixed_count,
                "by_type": self.issues_by_type(),
            },
            "results": [res.to_dict() for res in self.results],
        }
