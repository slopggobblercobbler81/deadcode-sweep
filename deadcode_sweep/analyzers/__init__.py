"""Analyzers module for deadcode-sweep."""

from deadcode_sweep.analyzers.base import BaseAnalyzer
from deadcode_sweep.analyzers.python_analyzer import PythonAnalyzer
from deadcode_sweep.analyzers.javascript_analyzer import JavaScriptAnalyzer

__all__ = ["BaseAnalyzer", "PythonAnalyzer", "JavaScriptAnalyzer"]
