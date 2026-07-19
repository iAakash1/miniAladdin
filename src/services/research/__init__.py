"""Provider-agnostic research layer.

Public surface: the engine. Nothing outside this package should import a
concrete provider — that is what makes providers swappable.
"""

from src.services.research.engine import (  # noqa: F401
    health,
    research_company,
    reset_for_tests,
    search,
)
