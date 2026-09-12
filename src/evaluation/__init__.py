"""Offline, reproducible evaluation of the grounded architecture."""

from src.evaluation.harness import (
    Configuration, EvaluationReport, Metrics, evaluate, run_scenario, summary_table,
)
from src.evaluation.scenarios import SCENARIO_SET_VERSION, Scenario, scenarios

__all__ = [
    "Configuration", "EvaluationReport", "Metrics", "SCENARIO_SET_VERSION",
    "Scenario", "evaluate", "run_scenario", "scenarios", "summary_table",
]
