"""
deadcode-sweep: Fast static analyzer for Python and JavaScript codebases.
Detects unused functions, unreachable code, and orphaned imports.
"""

__version__ = "0.1.0"
__author__ = "slopggobblercobbler81"
__license__ = "MIT"

from deadcode_sweep.models import (
    Issue,
    IssueType,
    Severity,
    Location,
    AnalysisResult,
    Report,
)
from deadcode_sweep.scanner import Scanner

__all__ = [
    "__version__",
    "Issue",
    "IssueType",
    "Severity",
    "Location",
    "AnalysisResult",
    "Report",
    "Scanner",
]
