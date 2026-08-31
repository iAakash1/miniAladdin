"""OmniSignal core package.

Public convenience exports are resolved lazily. Importing a narrow module such
as ``src.quant.models.trees`` must not import the entire product stack: model
artifacts unpickle through that module in the inference service, whose runtime
intentionally excludes provider, reporting, and data-ingestion dependencies.
"""

from importlib import import_module
from typing import Any

__version__ = "1.0.0"
__all__ = [
    "MacroIndicators",
    "RiskAssessment",
    "SentimentResult",
    "TechnicalAnalysis",
    "OmniSignalReport",
    "OmniSignalRiskEngine",
    "RiskAwarePredictionAgent",
    "SentimentAnalyzer",
    "AsyncDataPipeline",
    "OmniSignalReportGenerator",
]

_EXPORT_MODULES = {
    "MacroIndicators": "src.models",
    "RiskAssessment": "src.models",
    "SentimentResult": "src.models",
    "TechnicalAnalysis": "src.models",
    "OmniSignalReport": "src.models",
    "OmniSignalRiskEngine": "src.risk_analysis",
    "RiskAwarePredictionAgent": "src.prediction_agent",
    "SentimentAnalyzer": "src.sentiment_edge",
    "AsyncDataPipeline": "src.data_pipeline",
    "OmniSignalReportGenerator": "src.report_generator",
}


def __getattr__(name: str) -> Any:
    """Load a convenience export only when a caller asks for it."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
