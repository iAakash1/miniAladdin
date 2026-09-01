/**
 * Wire types for `/api/quant/*`.
 *
 * These describe what the backend sends. They deliberately do not model any
 * derived quantity: everything scientific — rank IC, spread curve, verdict,
 * promotion eligibility — arrives already computed, because a second
 * implementation in TypeScript would eventually disagree with the Python one.
 */

export interface Gate {
  observed: number | boolean | null
  required: string
  passed: boolean
}

export interface Verdict {
  label: string
  reason: string
  gates: Record<string, Gate>
}

export interface LeaderRow {
  model_id: string
  kind?: string
  mean_ic?: number | null
  ic_t_stat?: number | null
  train_mean_ic?: number | null
  train_ic_gap?: number | null
  fold_ic_positive_rate?: number | null
  gross_sharpe?: number | null
  net_sharpe?: number | null
  max_drawdown?: number | null
  annualised_turnover?: number | null
  cost_share_of_gross?: number | null
  deflated_sharpe_probability?: number | null
  deflated_sharpe_trials?: number | null
  beats_best_baseline?: boolean | null
  is_overfit_control?: boolean
  verdict: Verdict
}

export interface ArmRow {
  arm: string
  families: string[]
  hypothesis: string
  skipped: boolean
  reason?: string
  feature_count: number
  best_model?: string | null
  best_ic?: number | null
  best_t?: number | null
  models: Array<{ model_id: string; mean_ic?: number | null; ic_t_stat?: number | null }>
}

export interface Contrast {
  arm: string
  families_added: string[]
  mean_delta?: number | null
  median_delta?: number | null
  models_improved: number
  models_compared: number
}

export interface RegimeRow {
  regime: string
  dates: number
  observations: number
  mean_ic?: number | null
  ic_t_stat?: number | null
}

export interface FoldRow {
  index: number
  train_start: string
  train_end: string
  purge_end: string
  validation_start: string
  validation_end: string
  train_rows: number
  validation_rows: number
  train_symbols: number
  validation_symbols: number
  gap_sessions: number
  label_horizon_sessions: number
  embargo_sessions: number
}

export interface DatasetSource {
  dataset_id: string
  role: string
  rows: number
  min_date: string
  max_date: string
  point_in_time_status?: string
  survivorship_status?: string
}

export interface CostRow {
  half_spread_bps: number
  net_sharpe?: number | null
  gross_sharpe?: number | null
  cost_share_of_gross?: number | null
  annualised_turnover?: number | null
}

export interface Experiment {
  status: string
  detail?: string
  remedy?: string
  experiment_id?: string
  void?: boolean
  void_reason?: string
  definition?: Record<string, unknown>
  fingerprint?: string
  generated_at?: string
  git_commit?: string
  machine?: Record<string, unknown>
  runtime_seconds?: number
  dataset?: Record<string, unknown>
  dataset_sources?: DatasetSource[]
  universe?: Record<string, unknown>
  features_used?: string[]
  integrity?: {
    clean?: boolean
    rows_compared?: number
    columns_compared?: number
    cutoffs?: string[]
  }
  negative_controls?: {
    controls?: Array<{
      control: string; mean_ic: number; t_stat: number
      blocking: boolean; passed: boolean; role?: string
    }>
    blocking_failed?: string[]
    interpretation?: string
  }
  holdout?: { start?: string; end?: string; sessions?: number; touched?: boolean }
  regimes?: { distribution?: Record<string, number> }
  primary_target?: string
  leaderboard?: LeaderRow[]
  best_candidate?: LeaderRow | null
  best_baseline?: LeaderRow | null
  fold_rows?: FoldRow[]
  cost_sensitivity?: Record<string, CostRow[]>
  regime_performance?: Record<string, RegimeRow[]>
  /** Six-factor attribution per model. The alpha t-stat lives here and
   *  nowhere else — a leaderboard cannot show it. */
  factor_attribution?: Record<string, { alpha_t_stat?: number | null;
    alpha_annualised?: number | null; methodology?: string | null }> | null
  probability_of_backtest_overfitting?: {
    pbo?: number | null; configurations?: number; aligned_periods?: number
  }
  experiment_distribution?: {
    experiments?: number; best?: number; median?: number; above_zero?: number
  }
  trials_used_for_correction?: number
  ablation?: {
    ran: boolean
    arms?: ArmRow[]
    contrasts?: Contrast[]
    base_arm?: string
    interpretation?: string
  }
}

export interface QuantStatus {
  deployment_status: string
  message: string
  production: number
  candidates: number
  validated: number
  retired: number
  total_entries: number
  firewall?: {
    /** ARMED | NOT_ARMED | UNKNOWN. Prefer this over `contract_armed`: a false
     *  `contract_armed` can mean "confirmed not armed" or "contract could not
     *  be read", and a holdout must never be described more confidently than it
     *  is known. */
    contract_state?: 'ARMED' | 'NOT_ARMED' | 'UNKNOWN'
    contract_readable?: boolean
    headline?: string
    contract_armed?: boolean
    window?: { start?: string | null; end?: string | null }
  }
}

export interface ExperimentIndexRow {
  experiment_id: string
  void: boolean
  void_reason?: string | null
  status?: string
  objective?: string
  generated_at?: string
  dataset_version?: string
  rows?: number
  feature_count?: number
  cumulative_evaluations?: number
}

export interface ModelSeries {
  folds?: {
    folds: Array<{ fold: number; mean_ic: number | null; dates: number }>
    ic_by_date: Array<{ date: string; ic: number }>
  }
  spread_curve?: {
    status: string
    units: string
    periods: Array<{
      date: string
      gross_cumulative: number
      net_cumulative: number
      net_drawdown: number
    }>
    summary?: Record<string, number>
  }
}

export interface RegistryView {
  entries?: number
  by_status?: Record<string, number>
}
