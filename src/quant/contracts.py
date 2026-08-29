"""Auditable domain contracts for the quantitative research pipeline.

These models deliberately separate observations, forecasts, portfolio views,
targets, and execution artifacts.  A prediction is never an order, and every
stage carries stable identifiers that can be linked by the lineage service.

The contracts contain no provider, optimizer, model, or broker imports.  That
keeps the ordinary research API usable when optional quant dependencies are
not installed and gives future models one stable integration boundary.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp (never a naive wall clock)."""

    return datetime.now(timezone.utc)


class QuantModel(BaseModel):
    """Strict base model used by every persisted/public quant contract."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DataKind(str, Enum):
    OBSERVED = "observed"
    DERIVED = "derived"
    MODEL_PREDICTED = "model_predicted"


class QualityStatus(str, Enum):
    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    CONFIGURED = "configured"
    UNAVAILABLE = "unavailable"
    NOT_ENTITLED = "not_entitled"
    UNSUPPORTED = "unsupported"


class PriceBasis(str, Enum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN_ADJUSTED = "total_return_adjusted"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    CREATED = "created"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ModelStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    VALIDATED = "validated"
    PRODUCTION_CANDIDATE = "production_candidate"
    PRODUCTION = "production"
    RETIRED = "retired"


class OptimizationMethod(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    INVERSE_VOLATILITY = "inverse_volatility"
    RISK_PARITY = "risk_parity"
    MEAN_VARIANCE = "mean_variance"
    MEAN_CVAR = "mean_cvar"
    BLACK_LITTERMAN = "black_litterman"
    HIERARCHICAL_RISK_PARITY = "hierarchical_risk_parity"


class CovarianceMethod(str, Enum):
    SAMPLE = "sample"
    EWMA = "ewma"
    SHRINKAGE = "shrinkage"


class SourceRef(QuantModel):
    """One immutable source observation or dataset snapshot reference."""

    source_id: str = Field(min_length=1, max_length=160)
    provider: str = Field(min_length=1, max_length=80)
    dataset: str = Field(min_length=1, max_length=120)
    dataset_version: str | None = Field(default=None, max_length=160)
    retrieved_at: datetime
    checksum: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{32,128}$")
    uri: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TemporalContext(QuantModel):
    """The distinct clocks needed to make point-in-time claims testable."""

    event_time: datetime
    as_of_time: datetime
    published_at: datetime | None = None
    effective_at: datetime | None = None
    ingested_at: datetime = Field(default_factory=utc_now)
    period_start: date | None = None
    period_end: date | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "TemporalContext":
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        for name in ("event_time", "as_of_time", "published_at", "effective_at", "ingested_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        return self

    def available_by(self, cutoff: datetime) -> bool:
        """Whether every relevant availability clock is known by ``cutoff``."""

        if cutoff.tzinfo is None:
            raise ValueError("cutoff must be timezone-aware")
        clocks = [self.event_time]
        if self.published_at is not None:
            clocks.append(self.published_at)
        if self.effective_at is not None:
            clocks.append(self.effective_at)
        return max(clocks) <= cutoff


class MarketBar(QuantModel):
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9.$:_-]+$")
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = Field(default=None, ge=0)
    vwap: float | None = Field(default=None, gt=0)
    basis: PriceBasis
    adjustment_version: str | None = Field(default=None, max_length=120)
    temporal: TemporalContext
    sources: list[SourceRef] = Field(min_length=1)
    quality: QualityStatus = QualityStatus.VALID
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "MarketBar":
        values = (self.open, self.high, self.low, self.close)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError("OHLC values must be finite and positive")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high is below another OHLC value")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low is above another OHLC value")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timestamp != self.temporal.event_time:
            raise ValueError("timestamp must equal temporal.event_time")
        if self.basis is not PriceBasis.RAW and not self.adjustment_version:
            raise ValueError("adjusted bars require adjustment_version")
        return self


class CorporateAction(QuantModel):
    action_id: str = Field(min_length=1, max_length=160)
    symbol: str = Field(min_length=1, max_length=32)
    action_type: Literal["split", "cash_dividend", "symbol_change"]
    ex_date: date
    effective_at: datetime
    ratio: float | None = Field(default=None, gt=0)
    amount: float | None = Field(default=None, ge=0)
    old_symbol: str | None = None
    new_symbol: str | None = None
    sources: list[SourceRef] = Field(min_length=1)


class FactorDefinition(QuantModel):
    factor_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=600)
    category: str = Field(min_length=1, max_length=80)
    frequency: str = Field(min_length=1, max_length=40)
    lookback_sessions: int | None = Field(default=None, ge=1)
    required_inputs: list[str] = Field(min_length=1)
    point_in_time_safe: bool
    normalization: str = Field(min_length=1, max_length=120)
    direction: Literal["positive", "negative", "two_sided", "descriptive"]
    version: str = Field(min_length=1, max_length=80)
    formula: str = Field(min_length=1, max_length=1000)


class FactorObservation(QuantModel):
    observation_id: str = Field(min_length=1, max_length=160)
    factor_id: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=32)
    value: float | None
    temporal: TemporalContext
    source_observation_ids: list[str] = Field(min_length=1)
    calculation_version: str = Field(min_length=1, max_length=80)
    kind: Literal[DataKind.DERIVED] = DataKind.DERIVED
    quality: QualityStatus
    missing_reason: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def validate_value(self) -> "FactorObservation":
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("factor value must be finite")
        if self.value is None and not self.missing_reason:
            raise ValueError("a missing factor requires missing_reason")
        return self


class InputWindow(QuantModel):
    start: datetime
    end: datetime
    observations: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> "InputWindow":
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("input-window timestamps must be timezone-aware")
        if self.start > self.end:
            raise ValueError("input-window start must not be after end")
        return self


class CalibrationEvidence(QuantModel):
    evaluated_observations: int = Field(ge=0)
    mae: float | None = Field(default=None, ge=0)
    rmse: float | None = Field(default=None, ge=0)
    directional_accuracy: float | None = Field(default=None, ge=0, le=1)
    interval_coverage: float | None = Field(default=None, ge=0, le=1)
    regime_compatibility: float | None = Field(default=None, ge=0, le=1)
    evaluated_through: datetime | None = None


class ForecastDistribution(QuantModel):
    forecast_id: UUID = Field(default_factory=uuid4)
    symbol: str = Field(min_length=1, max_length=32)
    generated_at: datetime = Field(default_factory=utc_now)
    as_of_time: datetime
    horizon_sessions: int = Field(ge=1, le=252)
    forecast_timestamps: list[datetime] = Field(min_length=1)
    expected_return: float
    return_std: float = Field(ge=0)
    quantiles: dict[str, float]
    price_paths: list[list[float]] = Field(min_length=1)
    model_id: str = Field(min_length=1, max_length=160)
    model_version: str = Field(min_length=1, max_length=120)
    input_window: InputWindow
    data_snapshot_id: str = Field(min_length=1, max_length=160)
    random_seed: int
    sample_count: int = Field(ge=1)
    calibration: CalibrationEvidence | None = None
    source_observation_ids: list[str] = Field(min_length=1)
    quality: QualityStatus = QualityStatus.WARNING
    warnings: list[str] = Field(default_factory=list)
    kind: Literal[DataKind.MODEL_PREDICTED] = DataKind.MODEL_PREDICTED

    @model_validator(mode="after")
    def validate_distribution(self) -> "ForecastDistribution":
        if self.generated_at.tzinfo is None or self.as_of_time.tzinfo is None:
            raise ValueError("forecast timestamps must be timezone-aware")
        if not math.isfinite(self.expected_return) or not math.isfinite(self.return_std):
            raise ValueError("forecast moments must be finite")
        if len(self.forecast_timestamps) != self.horizon_sessions:
            raise ValueError("forecast_timestamps must match horizon_sessions")
        if any(ts.tzinfo is None or ts <= self.as_of_time for ts in self.forecast_timestamps):
            raise ValueError("forecast timestamps must be aware and after as_of_time")
        if len(self.price_paths) != self.sample_count:
            raise ValueError("price_paths must match sample_count")
        for path in self.price_paths:
            if len(path) != self.horizon_sessions:
                raise ValueError("every price path must match horizon_sessions")
            if any(not math.isfinite(value) or value <= 0 for value in path):
                raise ValueError("forecast prices must be finite and positive")
        required = {"p05", "p25", "p50", "p75", "p95"}
        if not required.issubset(self.quantiles):
            raise ValueError("quantiles require p05/p25/p50/p75/p95")
        ordered = [self.quantiles[key] for key in ("p05", "p25", "p50", "p75", "p95")]
        if any(not math.isfinite(value) for value in ordered) or ordered != sorted(ordered):
            raise ValueError("forecast quantiles must be finite and ordered")
        return self


class ConfidenceComponent(QuantModel):
    name: str = Field(min_length=1, max_length=80)
    value: float = Field(ge=0, le=1)
    methodology: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(default_factory=list)


class PortfolioView(QuantModel):
    view_id: UUID = Field(default_factory=uuid4)
    symbol: str = Field(min_length=1, max_length=32)
    as_of_time: datetime
    horizon_sessions: int = Field(ge=1, le=252)
    expected_return: float
    uncertainty: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    confidence_components: list[ConfidenceComponent] = Field(min_length=1)
    forecast_id: UUID | None = None
    source_signal_ids: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_numbers(self) -> "PortfolioView":
        if not math.isfinite(self.expected_return) or not math.isfinite(self.uncertainty):
            raise ValueError("view moments must be finite")
        if self.as_of_time.tzinfo is None:
            raise ValueError("as_of_time must be timezone-aware")
        return self


class PortfolioConstraints(QuantModel):
    long_only: bool = True
    fully_invested: bool = True
    min_weight: float = Field(default=0, ge=-1, le=1)
    max_weight: float = Field(default=0.25, gt=0, le=1)
    max_gross_exposure: float = Field(default=1, gt=0, le=5)
    max_net_exposure: float = Field(default=1, ge=-5, le=5)
    max_turnover: float = Field(default=0.5, ge=0, le=2)
    cash_minimum: float = Field(default=0, ge=0, le=1)
    max_portfolio_volatility: float | None = Field(default=None, gt=0)
    min_average_dollar_volume: float | None = Field(default=None, ge=0)
    sector_limits: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bounds(self) -> "PortfolioConstraints":
        if self.long_only and self.min_weight < 0:
            raise ValueError("long_only constraints cannot have a negative min_weight")
        if self.min_weight > self.max_weight:
            raise ValueError("min_weight must not exceed max_weight")
        if self.cash_minimum + self.max_weight < 0:
            raise ValueError("invalid cash/weight bounds")
        if any(limit <= 0 or limit > 1 for limit in self.sector_limits.values()):
            raise ValueError("sector limits must be in (0, 1]")
        return self


class OptimizationRequest(QuantModel):
    request_id: UUID = Field(default_factory=uuid4)
    as_of_time: datetime
    method: OptimizationMethod
    covariance_method: CovarianceMethod = CovarianceMethod.SHRINKAGE
    returns: dict[str, list[float]]
    views: list[PortfolioView] = Field(default_factory=list)
    current_weights: dict[str, float] = Field(default_factory=dict)
    benchmark_weights: dict[str, float] = Field(default_factory=dict)
    sectors: dict[str, str] = Field(default_factory=dict)
    average_dollar_volume: dict[str, float] = Field(default_factory=dict)
    constraints: PortfolioConstraints = Field(default_factory=PortfolioConstraints)
    capital: float = Field(gt=0)
    risk_aversion: float = Field(default=1, gt=0)
    transaction_cost_bps: float = Field(default=5, ge=0)
    data_snapshot_id: str = Field(min_length=1, max_length=160)
    run_id: UUID = Field(default_factory=uuid4)

    @model_validator(mode="after")
    def validate_return_panel(self) -> "OptimizationRequest":
        if self.as_of_time.tzinfo is None:
            raise ValueError("as_of_time must be timezone-aware")
        if not self.returns:
            raise ValueError("returns cannot be empty")
        lengths = {len(values) for values in self.returns.values()}
        if len(lengths) != 1 or min(lengths) < 2:
            raise ValueError("return series must be aligned and contain at least two rows")
        if any(not math.isfinite(value) for values in self.returns.values() for value in values):
            raise ValueError("returns must be finite")
        unknown = {view.symbol for view in self.views} - set(self.returns)
        if unknown:
            raise ValueError(f"views contain symbols outside returns: {sorted(unknown)}")
        return self


class ConstraintDiagnostic(QuantModel):
    constraint: str
    passed: bool
    observed: float | str | None = None
    limit: float | str | None = None
    message: str


class PortfolioTarget(QuantModel):
    target_id: UUID = Field(default_factory=uuid4)
    optimization_run_id: UUID
    as_of_time: datetime
    method: OptimizationMethod
    weights: dict[str, float]
    cash_weight: float = Field(ge=0, le=1)
    expected_return: float | None = None
    expected_volatility: float | None = Field(default=None, ge=0)
    cvar_95: float | None = Field(default=None, ge=0)
    turnover: float = Field(ge=0)
    estimated_transaction_cost: float = Field(ge=0)
    risk_contributions: dict[str, float] = Field(default_factory=dict)
    active_weights: dict[str, float] = Field(default_factory=dict)
    diagnostics: list[ConstraintDiagnostic] = Field(default_factory=list)
    optimizer_version: str = Field(min_length=1, max_length=120)
    covariance_snapshot_id: str | None = None
    source_view_ids: list[UUID] = Field(default_factory=list)
    data_snapshot_id: str = Field(min_length=1, max_length=160)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_weights(self) -> "PortfolioTarget":
        if self.as_of_time.tzinfo is None:
            raise ValueError("as_of_time must be timezone-aware")
        if not self.weights:
            raise ValueError("weights cannot be empty")
        if any(not math.isfinite(value) for value in self.weights.values()):
            raise ValueError("weights must be finite")
        total = sum(self.weights.values()) + self.cash_weight
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"weights plus cash must sum to 1 (got {total})")
        for name in ("expected_return", "expected_volatility", "cvar_95"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        return self


class OrderIntent(QuantModel):
    intent_id: UUID = Field(default_factory=uuid4)
    symbol: str = Field(min_length=1, max_length=32)
    side: Side
    as_of_time: datetime
    price_as_of_time: datetime
    reference_price: float = Field(gt=0)
    current_weight: float
    target_weight: float
    current_quantity: float
    target_quantity: float
    delta_quantity: float
    estimated_notional: float = Field(gt=0)
    estimated_transaction_cost: float = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    portfolio_target_id: UUID
    research_run_id: UUID | None = None
    forecast_ids: list[UUID] = Field(default_factory=list)
    paper_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_direction(self) -> "OrderIntent":
        values = (
            self.reference_price,
            self.current_weight,
            self.target_weight,
            self.current_quantity,
            self.target_quantity,
            self.delta_quantity,
            self.estimated_notional,
            self.estimated_transaction_cost,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("order intent values must be finite")
        if self.side is Side.BUY and self.delta_quantity <= 0:
            raise ValueError("buy intent requires positive delta_quantity")
        if self.side is Side.SELL and self.delta_quantity >= 0:
            raise ValueError("sell intent requires negative delta_quantity")
        if self.as_of_time.tzinfo is None or self.price_as_of_time.tzinfo is None:
            raise ValueError("order timestamps must be timezone-aware")
        if self.price_as_of_time > self.as_of_time:
            raise ValueError("reference price cannot come from the future")
        return self


class PaperOrder(QuantModel):
    order_id: UUID = Field(default_factory=uuid4)
    intent_id: UUID
    created_at: datetime = Field(default_factory=utc_now)
    status: OrderStatus = OrderStatus.CREATED
    requested_quantity: float = Field(gt=0)
    filled_quantity: float = Field(default=0, ge=0)
    rejection_reason: str | None = None
    paper_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_fill_quantity(self) -> "PaperOrder":
        if self.filled_quantity > self.requested_quantity:
            raise ValueError("filled quantity cannot exceed requested quantity")
        return self


class Fill(QuantModel):
    fill_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    intent_id: UUID
    symbol: str
    side: Side
    timestamp: datetime
    quantity: float = Field(gt=0)
    reference_price: float = Field(gt=0)
    fill_price: float = Field(gt=0)
    gross_notional: float = Field(gt=0)
    commission: float = Field(ge=0)
    spread_cost: float = Field(ge=0)
    slippage_cost: float = Field(ge=0)
    market_impact_cost: float = Field(ge=0)
    paper_only: Literal[True] = True

    @property
    def total_cost(self) -> float:
        return self.commission + self.spread_cost + self.slippage_cost + self.market_impact_cost


class RiskSnapshot(QuantModel):
    risk_id: UUID = Field(default_factory=uuid4)
    as_of_time: datetime
    data_snapshot_id: str
    covariance_method: CovarianceMethod
    covariance_window: int = Field(ge=2)
    annualization_factor: int = Field(default=252, gt=0)
    portfolio_volatility: float = Field(ge=0)
    downside_volatility: float = Field(ge=0)
    var_95: float = Field(ge=0)
    cvar_95: float = Field(ge=0)
    max_drawdown: float = Field(ge=0, le=1)
    concentration_hhi: float = Field(ge=0)
    gross_exposure: float = Field(ge=0)
    net_exposure: float
    risk_contributions: dict[str, float]
    warnings: list[str] = Field(default_factory=list)


class DatasetSnapshot(QuantModel):
    snapshot_id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=120)
    dataset: str = Field(min_length=1, max_length=120)
    source_version: str | None = None
    schema_version: str
    retrieved_at: datetime
    min_event_time: datetime | None = None
    max_event_time: datetime | None = None
    row_count: int = Field(ge=0)
    symbol_count: int | None = Field(default=None, ge=0)
    checksum: str | None = None
    transformations: list[str] = Field(default_factory=list)
    adjustment_rules: list[str] = Field(default_factory=list)
    point_in_time_status: QualityStatus
    survivorship_status: QualityStatus
    raw_immutable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class WalkForwardSplit(QuantModel):
    split_id: str
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date | None = None
    test_end: date | None = None
    purge_sessions: int = Field(default=0, ge=0)
    embargo_sessions: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_chronology(self) -> "WalkForwardSplit":
        if self.train_start > self.train_end:
            raise ValueError("invalid train range")
        if self.validation_start > self.validation_end or self.validation_start <= self.train_end:
            raise ValueError("validation must follow training")
        if (self.test_start is None) != (self.test_end is None):
            raise ValueError("test_start and test_end must be provided together")
        if self.test_start and (self.test_start > self.test_end or self.test_start <= self.validation_end):
            raise ValueError("test must follow validation")
        return self


class RunRecord(QuantModel):
    run_id: UUID = Field(default_factory=uuid4)
    run_type: Literal["research", "forecast", "optimization", "backtest", "execution"]
    status: RunStatus = RunStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    git_commit: str | None = Field(default=None, max_length=64)
    random_seed: int | None = None
    data_snapshot_ids: list[str] = Field(default_factory=list)
    parent_run_ids: list[UUID] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = Field(default=None, max_length=2000)
    runtime_ms: float | None = Field(default=None, ge=0)


class ModelRecord(QuantModel):
    model_id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=1, max_length=160)
    status: ModelStatus = ModelStatus.EXPERIMENTAL
    artifact_location: str | None = Field(default=None, max_length=500)
    input_schema: str
    output_schema: str
    feature_contract: list[str] = Field(default_factory=list)
    dataset_snapshot_ids: list[str] = Field(default_factory=list)
    training_range: tuple[date, date] | None = None
    validation_methodology: str | None = None
    validation_metrics: dict[str, float | int | None] = Field(default_factory=dict)
    test_metrics: dict[str, float | int | None] = Field(default_factory=dict)
    git_commit: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def prevent_unvalidated_production(self) -> "ModelRecord":
        if self.status in {ModelStatus.PRODUCTION_CANDIDATE, ModelStatus.PRODUCTION}:
            if not self.validation_methodology or not self.test_metrics:
                raise ValueError("production candidates require methodology and untouched test metrics")
        return self


class LineageEdge(QuantModel):
    parent_type: str
    parent_id: str
    child_type: str
    child_id: str
    transformation: str = Field(min_length=1, max_length=300)
    recorded_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

