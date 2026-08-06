"""
Research analytics — evaluating whether the engine's factors actually work.

Distinct from `src/scoring/` (which decides) and `src/panel/` (which stores).
This package only ever *reads* the point-in-time panel and reports what the
evidence supports, including when the evidence says a factor does not work.
"""

from src.research.portfolio import PortfolioResult, simulate
from src.research.screen import ScreenRow, dispersion, screen
from src.research.attribution import Attribution, attribute
from src.research.redundancy import Redundancy
from src.research.redundancy import analyse as analyse_redundancy
from src.research.stability import Stability, analyse
from src.research.cross_section import (
    Evaluation,
    evaluate_factor,
    forward_returns,
    newey_west_tstat,
    quantile_spread,
    rank_cross_section,
    spearman_ic,
)

__all__ = [
    "Attribution",
    "Evaluation",
    "attribute",
    "PortfolioResult",
    "ScreenRow",
    "Redundancy",
    "Stability",
    "analyse_redundancy",
    "analyse",
    "dispersion",
    "screen",
    "simulate",
    "evaluate_factor",
    "forward_returns",
    "newey_west_tstat",
    "quantile_spread",
    "rank_cross_section",
    "spearman_ic",
]
