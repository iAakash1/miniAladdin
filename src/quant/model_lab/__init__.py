"""Exploratory, resumable nested-CV model research.

MODEL-LAB is a separate namespace from confirmatory EXP studies. Its artifacts
can nominate configurations for a later preregistered replication, but can
never promote a model or open the final holdout.
"""

from .registry import TrialRecord, TrialRegistry, TrialStatus

__all__ = ["TrialRecord", "TrialRegistry", "TrialStatus"]
