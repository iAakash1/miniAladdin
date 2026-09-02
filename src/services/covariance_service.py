"""Covariance estimator comparison, over the research book's own returns.

The named estimators exist in `src.quant.portfolio.covariance` and had no way
to reach a reader. This exposes them side by side, which is the only way the
choice between them is legible: the numbers a book reports depend on which one
produced the matrix, and a single estimator shown alone hides that dependence.

Every estimator runs on the same panel so the comparison is like for like. The
pairwise default is included precisely because it is the one that can fail to
be positive semi-definite — showing it beside three that cannot is the point.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.portfolio import psd
from src.quant.portfolio.covariance import ESTIMATORS, estimate
from src.quant.portfolio.diversification import diversification_ratio
from src.quant.portfolio.optimizer import covariance as pairwise_covariance


def _condition_number(matrix: np.ndarray) -> Optional[float]:
    """Ratio of largest to smallest eigenvalue.

    Large means the matrix is close to singular in some direction, which is
    where an optimiser puts its largest, least justified bets.
    """
    try:
        eigenvalues = np.linalg.eigvalsh(matrix)
    except np.linalg.LinAlgError:
        return None
    smallest = float(np.min(np.abs(eigenvalues)))
    if smallest <= 0 or not np.isfinite(smallest):
        return None
    return float(np.max(np.abs(eigenvalues)) / smallest)


def _describe(
    name: str,
    matrix: pd.DataFrame,
    weights: pd.Series,
    *,
    observations: int,
    complete_rows: Optional[int],
    shrinkage: Optional[float],
    note: Optional[str],
) -> dict[str, Any]:
    values = matrix.to_numpy()
    finite = bool(np.all(np.isfinite(values)))
    eigenvalues = np.linalg.eigvalsh(values) if finite else None
    minimum = float(eigenvalues.min()) if eigenvalues is not None else None
    is_psd = bool(minimum is not None and minimum >= -1e-12 * max(1.0, abs(float(eigenvalues.max()))))

    # The portfolio volatility this matrix implies, or the refusal it earns.
    volatility: Optional[float] = None
    refusal: Optional[str] = None
    diversification: Optional[float] = None
    try:
        aligned = weights.reindex(matrix.index).fillna(0.0)
        volatility = psd.volatility(aligned.to_numpy(), values, context=name)
        diversification = diversification_ratio(weights, matrix)
    except psd.NotPositiveSemiDefinite as exc:
        refusal = str(exc)

    # The diversification ratio is a weighted-average volatility over a
    # portfolio volatility, and correlation can only push the second below the
    # first. A value under 1 is therefore not a diversification result — it is
    # the matrix telling you it is not a covariance matrix. Flagged rather than
    # left for a reader to notice, because it looks like an ordinary number.
    impossible = (
        diversification is not None and diversification < 1.0 - 1e-9
    )

    return {
        "estimator": name,
        "names": int(matrix.shape[0]),
        "diversification_ratio_below_one": impossible,
        "impossible_reason": (
            "the diversification ratio cannot be below 1 for a valid covariance; "
            "this matrix is not positive semi-definite"
            if impossible else None
        ),
        "observations": observations,
        "complete_rows": complete_rows,
        "shrinkage": None if shrinkage is None else round(shrinkage, 6),
        "positive_semi_definite": is_psd,
        "min_eigenvalue": None if minimum is None else float(minimum),
        "condition_number": _condition_number(values) if finite else None,
        "non_finite_entries": int((~np.isfinite(values)).sum()),
        "portfolio_volatility": None if volatility is None else round(volatility, 8),
        "diversification_ratio": None if diversification is None else round(diversification, 6),
        "unusable_reason": refusal,
        "note": note,
    }


def compare(returns: pd.DataFrame, weights: pd.Series) -> dict[str, Any]:
    """Every named estimator on one panel, plus the pairwise default."""
    rows: list[dict[str, Any]] = []

    # The shipped default first, because it is the baseline everything else is
    # being compared against — including on the property it can fail.
    pairwise = pairwise_covariance(returns)
    rows.append(
        _describe(
            "pairwise (default)", pairwise, weights,
            observations=int(len(returns)), complete_rows=None,
            shrinkage=None,
            note=(
                "pandas pairwise deletion: each entry uses whichever rows that "
                "pair shares, so entries come from different populations"
            ),
        )
    )

    for name in sorted(ESTIMATORS):
        result = estimate(returns, estimator=name)
        rows.append(
            _describe(
                name, result.matrix, weights,
                observations=result.observations,
                complete_rows=result.complete_rows,
                shrinkage=result.shrinkage,
                note=result.note,
            )
        )

    return {
        "estimators": rows,
        "panel": {
            "names": int(returns.shape[1]),
            "rows": int(returns.shape[0]),
            "complete_rows": int(returns.dropna(axis=0, how="any").shape[0]),
        },
        "note": (
            "Every estimator runs on the same panel. The default is included "
            "because it is the one that can fail to be positive semi-definite; "
            "an estimator shown alone hides that the reported risk depends on "
            "which matrix produced it. Nothing here changes the default."
        ),
    }


def correlation_view(returns: pd.DataFrame, *, estimator: str = "empirical") -> dict[str, Any]:
    """A correlation matrix with unmeasured pairs left as null.

    Null rather than zero. An unobserved pair is not an uncorrelated pair, and
    the difference is the whole reason the redundancy verdict is withheld when
    coverage is thin.
    """
    result = estimate(returns, estimator=estimator)
    matrix = result.matrix
    sigma = np.sqrt(np.clip(np.diag(matrix.to_numpy()), 0.0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        outer = np.outer(sigma, sigma)
        correlation = np.where(outer > 0, matrix.to_numpy() / outer, np.nan)

    labels = [str(c) for c in matrix.columns]
    values = [
        [None if not np.isfinite(v) else round(float(v), 6) for v in row]
        for row in correlation
    ]
    return {
        "estimator": result.estimator,
        "labels": labels,
        "values": values,
        "observations": result.observations,
        "complete_rows": result.complete_rows,
        "note": result.note,
    }
