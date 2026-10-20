"""File scanner and orchestrator for deadcode-sweep."""

import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from deadcode_sweep.analyzers.base import BaseAnalyzer
from deadcode_sweep.analyzers.javascript_analyzer import JavaScriptAnalyzer
from deadcode_sweep.analyzers.python_analyzer import PythonAnalyzer
from deadcode_sweep.fixer import Fixer
from deadcode_sweep.models import (
    AnalysisResult,
    ProjectContext,
    Report,
)

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
    "egg-info",
    ".eggs",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
}


class Scanner:
    """Recursively discovers and analyzes files in targeted paths."""

    def __init__(
        self,
        lang: str = "all",
        ignore_dirs: Optional[Set[str]] = None,
        ignore_names: Optional[Set[str]] = None,
        include_public_functions: bool = False,
        fix: bool = False,
    ):
        self.lang = lang.lower()
        self.ignore_dirs = (ignore_dirs or set()) | DEFAULT_IGNORE_DIRS
        self.ignore_names = ignore_names or set()
        self.include_public_functions = include_public_functions
        self.fix = fix

        # Setup active analyzers
        self.analyzers: List[BaseAnalyzer] = []
        if self.lang in ("all", "python", "py"):
            self.analyzers.append(PythonAnalyzer())
        if self.lang in ("all", "javascript", "js", "ts", "typescript"):
            self.analyzers.append(JavaScriptAnalyzer())

        # Extension map
        self.ext_map: Dict[str, BaseAnalyzer] = {}
        for analyzer in self.analyzers:
            for ext in analyzer.supported_extensions:
                self.ext_map[ext] = analyzer

    def is_dir_ignored(self, dir_name: str) -> bool:
        return dir_name in self.ignore_dirs or dir_name.endswith(".egg-info")

    def discover_files(self, paths: List[str]) -> List[Tuple[str, BaseAnalyzer]]:
        """Find all matching files and their corresponding analyzer."""
        discovered: List[Tuple[str, BaseAnalyzer]] = []
        seen_paths: Set[str] = set()

        for target in paths:
            path_obj = Path(target)
            if not path_obj.exists():
                continue

            if path_obj.is_file():
                ext = path_obj.suffix.lower()
                analyzer = self.ext_map.get(ext)
                if analyzer and str(path_obj.resolve()) not in seen_paths:
                    seen_paths.add(str(path_obj.resolve()))
                    discovered.append((str(path_obj), analyzer))
            elif path_obj.is_dir():
                for root, dirs, files in os.walk(str(path_obj)):
                    # Prune ignored directories in-place
                    dirs[:] = [d for d in dirs if not self.is_dir_ignored(d)]

                    for file_name in files:
                        _, ext = os.path.splitext(file_name)
                        analyzer = self.ext_map.get(ext.lower())
                        if analyzer:
                            full_path = os.path.join(root, file_name)
                            resolved = str(Path(full_path).resolve())
                            if resolved not in seen_paths:
                                seen_paths.add(resolved)
                                discovered.append((full_path, analyzer))

        # Sort paths for deterministic output
        discovered.sort(key=lambda x: x[0])
        return discovered

    def scan(self, paths: List[str]) -> Report:
        """Execute full scan across given paths."""
        start_time = time.time()
        file_list = self.discover_files(paths)

        total_files = len(file_list)
        total_lines = 0
        results: List[AnalysisResult] = []
        fixed_count = 0

        # Multi-file context
        context = ProjectContext() if total_files > 1 else None

        # Pass 1: Collect symbols across all files if multi-file scan
        file_contents: Dict[str, str] = {}
        if context is not None:
            for file_path, analyzer in file_list:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        code = f.read()
                    file_contents[file_path] = code
                    analyzer.collect_symbols(code, file_path, context)
                except Exception:
                    continue

        # Pass 2: Analyze each file
        for file_path, analyzer in file_list:
            if file_path in file_contents:
                code = file_contents[file_path]
            else:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        code = f.read()
                except Exception as e:
                    results.append(
                        AnalysisResult(
                            file_path=file_path,
                            lines_scanned=0,
                            parse_error=f"Could not read file: {e}",
                        )
                    )
                    continue

            total_lines += len(code.splitlines())
            result = analyzer.analyze_code(
                code=code,
                file_path=file_path,
                context=context,
                ignore_names=self.ignore_names,
                include_public_functions=self.include_public_functions,
            )

            # Auto-fix if requested
            if self.fix and result.issues:
                applied = Fixer.fix_file(file_path, result.issues)
                fixed_count += applied
                if applied > 0:
                    # Filter out fixed issues
                    result.issues = [
                        i for i in result.issues if not (i.fixable and i.issue_type.value == "orphaned_import")
                    ]

            results.append(result)

        duration = time.time() - start_time
        return Report(
            results=results,
            total_files=total_files,
            total_lines=total_lines,
            duration_seconds=duration,
            fixed_count=fixed_count,
        )
