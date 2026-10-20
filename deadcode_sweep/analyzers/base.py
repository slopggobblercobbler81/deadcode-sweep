"""Base classes for deadcode-sweep analyzers."""

from abc import ABC, abstractmethod
from typing import Optional, Set, Tuple

from deadcode_sweep.models import AnalysisResult, ProjectContext


class BaseAnalyzer(ABC):
    """Abstract base class for language-specific static analyzers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the analyzer (e.g., 'python', 'javascript')."""
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> Tuple[str, ...]:
        """Tuple of file extensions supported by this analyzer (e.g., ('.py',))."""
        pass

    @abstractmethod
    def analyze_code(
        self,
        code: str,
        file_path: str,
        context: Optional[ProjectContext] = None,
        ignore_names: Optional[Set[str]] = None,
        include_public_functions: bool = False,
    ) -> AnalysisResult:
        """
        Analyze the given code string and return an AnalysisResult.
        """
        pass

    @abstractmethod
    def collect_symbols(
        self,
        code: str,
        file_path: str,
        context: ProjectContext,
    ) -> None:
        """
        Pass 1 symbol collection for multi-file project analysis.
        """
        pass
