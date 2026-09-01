/**
 * Shapes served by `/api/quant/search/:id` and `/api/quant/selection/:id`.
 *
 * Every numeric field is nullable because the backend returns null rather than
 * a placeholder for anything it has not measured. The formatters render null as
 * an em dash, never as zero.
 */

export interface SearchConfigRow {
  config_id: string
  family: string
  stage: string
  arm: string | null
  target: string | null
  params: Record<string, unknown> | null
  feature_count: number | null
  mean_ic: number | null
  ic_t_stat: number | null
  ic_ir: number | null
  train_mean_ic: number | null
  train_ic_gap: number | null
  fold_ic_positive_rate: number | null
  folds: number | null
  seconds: number | null
  diagnosis: 'HEALTHY' | 'OVERFIT' | 'UNSTABLE' | 'UNDERFIT' | 'FAILED'
}

export interface SearchFamilyRow {
  family: string
  evaluated: number
  failed: number
  overfit: number
  best_ic: number | null
  best_t: number | null
  best_gap: number | null
  worst_gap: number | null
  seconds: number | null
}

export interface MultipleTesting {
  prior_trials: number | null
  new_trials: number | null
  cumulative_trials: number | null
  expected_max_abs_t_under_null: number | null
  bonferroni_threshold_5pct?: number | null
  observed_max_abs_t: number | null
  observed_clears_threshold: boolean | null
  provisional?: boolean
  basis?: string
  caveat?: string
  interpretation?: string
}

export interface SearchState {
  available: boolean
  experiment_id: string
  state: 'RUNNING' | 'COMPLETE' | 'NOT STARTED'
  detail?: string
  complete?: boolean
  configurations_evaluated?: number
  configurations_planned?: number | null
  configurations_failed?: number
  progress_pct?: number | null
  stages?: { stage: string; evaluated: number; failed: number; worker_seconds: number }[]
  families?: SearchFamilyRow[]
  diagnoses?: Record<string, number>
  leaderboard?: SearchConfigRow[]
  multiple_testing?: MultipleTesting
  budget?: Record<string, unknown> | null
  families_advanced?: string[] | null
  reference_context?: { arm: string; target: string } | null
  dataset?: Record<string, unknown> | null
  machine?: Record<string, unknown> | null
  package_versions?: Record<string, string | null> | null
  git_commit?: string | null
  git_dirty?: boolean | null
  workers?: number | null
  runtime_seconds?: number | null
  generated_at?: string | null
  holdout?: { touched?: boolean; note?: string; start?: string; end?: string } | null
  note?: string
}

export interface SelectionGate {
  gate: string
  passed: boolean
  observed: unknown
  required: string
}

export interface SelectionState {
  available: boolean
  experiment_id?: string
  detail?: string
  verdict?: {
    passed: boolean
    status: string
    gates: SelectionGate[]
    failed: string[]
    note: string
  }
  selected?: {
    config_id: string
    family: string
    params: Record<string, unknown>
    arm: string
    target: string
    ranked_by: string
  }
  economics?: Record<string, Record<string, unknown>>
  significance?: Record<string, {
    deflated_sharpe?: {
      observed_sharpe?: number | null
      deflated_probability?: number | null
      expected_max_sharpe_under_null?: number | null
      trials?: number | null
      skew?: number | null
      excess_kurtosis?: number | null
    }
    minimum_track_record?: {
      required_periods?: number | null
      observed_periods?: number | null
      sufficient?: boolean | null
    }
  }>
  multiple_testing?: MultipleTesting
  probability_of_backtest_overfitting?: {
    pbo?: number | null
    splits_evaluated?: number | null
    interpretation?: string | null
  }
  refit_reproduction?: {
    config_id: string
    search_mean_ic: number | null
    refit_mean_ic: number | null
    delta: number | null
    reproduces: boolean
  }[]
  holdout?: { touched?: boolean; note?: string }
  git_commit?: string | null
}
