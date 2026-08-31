"""Portfolio construction: signal + risk estimates -> weights.

Deliberately separate from `src/quant/models` (which produces signals) and from
`src/quant/backtest` (which executes them). Optimised weights allocate risk;
they are never predictive evidence.
"""
