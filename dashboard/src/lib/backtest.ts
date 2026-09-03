/**
 * The shape `/api/backtest/:ticker` serves.
 *
 * It lived inside a page component, so every other consumer had to import
 * from a view to describe a payload — which is what kept a retired page
 * alive after its route was gone. A response shape belongs beside the other
 * response shapes.
 */

export interface BacktestData {
  ticker: string
  scope_note: string
  samples: number
  period: { start: string; end: string }
  ic: number | null
  baseline_12_1_ic: number | null
  baseline_12_1_strategy: Record<string, number | null> | null
  rolling_ic: Array<{ date: string; ic: number }>
  recent: { rolling_ic_last: number | null; verdict_flips_last6: number }
  hit_rate: number | null
  directional_samples: number
  confusion_matrix: Record<'long' | 'flat' | 'short', { up: number; down: number }>
  calibration: Array<{ bin: string; expected: number; actual: number; n: number }>
  strategy: Record<string, number | null>
  buy_hold: Record<string, number | null>
  win_rate_invested_days: number | null
  avg_holding_days: number | null
  time_invested_pct: number
  equity_curve: Array<{ date: string; strategy: number; buy_hold: number }>
  monthly_strategy_returns: Record<string, number>
  score_distribution: Array<{ bin: string; count: number }>
  verdict_distribution: Record<string, number>
  factor_diagnostics: Record<string, { ic: number | null; sign_stability: number | null; samples: number }>
  factor_correlations: Record<string, number>
  prediction_drift_psi: number | null
  psi_note: string
  error?: string
}
