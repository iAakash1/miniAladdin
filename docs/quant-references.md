# External quant references

Open-source projects studied while building the quant layer. This records what
each contributed, what was deliberately **not** taken, and why — because a list
of links is not a design influence, and claiming to have implemented something a
reference merely mentions is worse than not reading it.

**Depth of inspection is stated per reference**, because it varies and pretending
otherwise would be the same failure the rest of this document exists to avoid.
Sections 1–5 were worked through in detail while their ideas were being
implemented. Sections 6–7 were read at documentation level during the EXP-007
design. Section 8 covers tools assessed as candidates rather than studied as
architectures.

**Rule applied throughout:** nothing is listed under "implemented" unless it
exists in this repository and is reachable. Where a concept only shaped a
decision, it is under "influenced". Where it was rejected, the reason is a
property of *this* project, not a criticism of the reference.

| Reference | Role in their stack | What we took |
|---|---|---|
| [skfolio](https://github.com/skfolio/skfolio) | Portfolio construction | Estimator/optimiser separation; allocator family |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Execution engine | Layer separation; deterministic clock discipline |
| [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | LLM oversight / research workflow | Grounding gate; hash-chained provenance; refuse-don't-default |
| [Kronos](https://github.com/shiyu-coder/Kronos) | Time-series foundation model | Probabilistic-forecast framing. **Model rejected** |
| [QuantFrame article](https://www.quantframe.io/article/open-source-hedge-fund-stack) | Assembles the four | The four-layer contract, and "the LLM is the analyst, not the trader" |
| [Qlib](https://github.com/microsoft/qlib) | Full research chain | Staged search shape; the Recorder discipline. **Expression engine rejected** |
| [FinRL / FinRL-Meta / ElegantRL](https://github.com/AI4Finance-Foundation/FinRL) | RL trading infrastructure | Layer separation confirmed. **RL rejected for this problem** |
| Tooling (XGBoost, LightGBM, CatBoost, PyTorch, cvxpy, mlfinlab, vectorbt, …) | Components | Boosters and torch adopted for the GPU worker; the rest assessed and declined |

---

## 1. skfolio

**What it solves.** Portfolio optimisation with a scikit-learn-compatible API:
`fit`/`predict` on portfolio models, composable estimators, and cross-validation
that returns portfolio objects rather than scores.

**Architecture.** The decisive idea is that **estimation and optimisation are
separate objects**. Covariance estimators (`EmpiricalPrior`, `LedoitWolf`,
`Denoising`, `GraphicalLassoCV`), expected-return estimators, and prior models
(`BlackLitterman`, `EntropyPooling`) are composed *into* an optimiser
(`MeanRisk`, `RiskBudgeting`, `HierarchicalRiskParity`,
`MaximumDiversification`) rather than living inside it.

### What we implemented

`src/quant/portfolio/optimizer.py`:

* **The estimator/optimiser split.** `covariance()` and `volatilities()` are
  standalone; every allocator takes estimates as arguments. The module has no
  access to a model and cannot produce a forecast. This is the single most
  valuable thing taken from skfolio, and it is why a covariance bug here is
  distinguishable from an allocation bug.
* **The allocator family**: `equal_weight`, `inverse_volatility`,
  `minimum_variance`, `maximum_diversification`, `risk_parity` (their
  `RiskBudgeting`), `mean_variance`, `volatility_target`.
* **A `Constraints` value object** — long-only, weight caps, cash floor,
  turnover limit, gross/net targets, group caps — applied to a fixed point and
  then *verified*, returning `feasible=False` with the violated constraint named.
* **Diversification ratio and effective-N diagnostics** alongside the weights,
  so an allocation can be argued with rather than accepted.

`src/quant/risk/engine.py` takes their **`RiskMeasure` enum discipline** — that a
risk number is meaningless without its measure — and hardens it: every metric
returns a `RiskMetric` carrying `method`, and `var_historical_95` /
`var_parametric_95` are separate fields that are never averaged.

### What we rejected

* **cvxpy and the convex solver core.** skfolio's exact CVaR minimisation,
  cardinality constraints and linear constraint expressions all need a solver.
  It is a heavy dependency for a repository whose research conclusion is that
  *no model has an edge worth allocating to*. Our `min_cvar_heuristic` is
  explicitly labelled **not LP-optimal** in its return payload rather than
  pretending otherwise. When a model clears the promotion gate, cvxpy is the
  correct next step.
* **Black-Litterman.** The article's design makes BL the research→portfolio
  contract. We have no forecast worth expressing as a view: EXP-006's alpha
  t-statistic is +0.047. Blending a zero-information view with equilibrium
  returns the equilibrium, and building the machinery would imply we had
  something to blend.
* **Hierarchical Risk Parity / NestedClusters.** Genuinely good, and defensible
  once there is a signal to allocate. Adding a clustering step now would add a
  tuning surface to a problem that does not have a solution yet.
* **Ledoit-Wolf shrinkage.** Deliberately omitted *and documented in the
  docstring*: it is a better estimator, and introducing it silently would change
  every historical risk number. It is a named future change, not an oversight.

---

## 2. NautilusTrader

**What it solves.** Deterministic event-driven trading where the same strategy
code runs in backtest, sandbox and live, eliminating the reimplementation gap
that introduces deployment risk.

**Architecture.** Rust core, Python orchestration; a central **message bus** and
**cache**; a deterministic **clock**; full order lifecycle (IOC/FOK/GTC/GTD, OCO,
OUO, OTO contingencies); portfolio and account state across venues.

### What we implemented

* **The layer separation, as an enforced boundary.** Signal
  (`src/quant/models`) → portfolio (`src/quant/portfolio`) → execution
  (`src/quant/backtest/engine.py`). Each direction is one-way: the optimiser
  cannot see a model, the risk engine cannot allocate. This is Nautilus's
  discipline applied at our scale.
* **Deterministic time.** `src/quant/pit/calendar.py` with
  `require_chronological()`, and the execution lag in
  `BacktestConfig.execution_lag_periods` which **refuses a value below 1** — a
  signal computed at the close of *t* forms a position at *t+1*. This is the
  same "the clock is not negotiable" principle, and it caught a real defect.
* **Cost realism as a first-class stage** rather than a post-hoc adjustment:
  `SimpleCostModel` charges commission, half-spread, slippage and square-root
  impact on *traded* notional, and `CostWaterfall` decomposes gross → net one
  layer at a time.

### What we rejected

* **The event-driven engine itself.** Our research operates on a rebalanced
  cross-sectional panel at a 5-session stride, not on a tick stream. An event
  loop, message bus and order lifecycle would be substantial machinery serving a
  model that trades a quintile book monthly and, on current evidence, should not
  trade at all.
* **The order lifecycle.** IOC/FOK/OCO semantics matter when you are placing
  orders. **There is no live-order path anywhere in this codebase, and none is
  planned in this phase.** Building one would create a risk surface with no
  offsetting benefit.
* **Rust.** The bottleneck here is the 116M-row option chain and the walk-forward
  fit, both already handled by Dolt aggregation and scikit-learn.

---

## 3. Vibe-Trading

**What it solves.** An LLM research agent with deterministic tool calls, over
market data, valuation and backtesting — with governance designed in.

**Architecture.** Agent layer over FastAPI/MCP services; a **grounding gate** that
refuses claims outside recorded OHLC ranges; **hash-chained append-only audit
ledgers**; per-run provenance; warm-up-bar separation against look-ahead.

### What we implemented

Several of its governance ideas were arrived at independently here and are
strengthened by the convergence:

* **Refuse rather than default.** Their valuation engines "refuse missing inputs
  rather than defaulting"; our `DatasetBuilder._admit` refuses a
  non-point-in-time source, `build_feature_audit` raises on an empty registry,
  and `optimize()` returns an infeasible `Allocation` rather than silently
  falling back to equal weight.
* **Immutable, append-only provenance.** `docs/RESEARCH_LEDGER.md` is append-only
  with a stated rule that **a void study stays in the ledger** — EXP-002 remains
  VOID and its 34 evaluations still count against every later significance claim.
  Same instinct as their hash-chained ledger.
* **Per-run manifests.** Every artifact carries dataset content hash, git SHA,
  seed, dependency versions and machine profile — their "hash manifests over
  prompts, skill registry, package versions", applied to experiments.
* **Look-ahead separation.** Their warm-up-bar separation is our purge + embargo
  + `HoldoutFirewall`.

### What we rejected

* **The LLM agent layer.** miniAladdin's research conclusions must be
  reproducible from a seed and a dataset hash. Inserting a language model into
  the path that decides what is significant makes that impossible, and this
  project has already voided one study over a reproducibility defect.
* **13+ broker connectors and live execution.** No live path. See above.
* **MCP tool surface.** Our equivalent is a typed HTTP API with a Python service
  layer, which is sufficient for one frontend.

---

## 4. Kronos

**What it solves.** A decoder-only transformer foundation model for OHLCV
candlesticks — 4.1M to 499.2M parameters, trained on 45 exchanges. A custom
tokenizer quantises continuous multi-dimensional K-line data into **hierarchical
discrete tokens**; the transformer then trains autoregressively on them.
`KronosPredictor` handles normalisation, tokenisation, sampling (`T`, `top_p`)
and denormalisation.

### What we implemented

* **Probabilistic framing over point forecasts.** Kronos samples multiple futures
  and reports a distribution. Our analogue is not a sampler but a discipline:
  every reported IC arrives with a Newey-West t-statistic, fold dispersion
  (`stability_ic`: min/max/std/positive-rate) and a deflated-Sharpe probability
  against the cumulative trial count. A point estimate without its dispersion is
  not reported anywhere.
* **The separation of representation from prediction** informed keeping the
  feature registry (103 features, each with lookback, direction hypothesis and a
  leakage test) independent of the model ladder.

### What we rejected — and this is the most important rejection here

**We did not adopt Kronos, and adopting it now would be indefensible on our own
evidence.**

* **EXP-005 measured that adding data makes results worse.** Options, analyst
  revisions and gated fundamentals each *lowered* IC against a 27-feature price
  base; the best arm was the one with no fundamental data at all. There is no
  reading of that result under which added model capacity is the missing piece.
* **A 100M-parameter transformer on 506,374 rows** is a capacity-to-data ratio
  that guarantees the train/validation gap this project already flags at 0.15.
  Our deliberately over-parameterised control (`gradient_boosting_deep`) sits at
  a **+0.729** gap — the diagnostic works, and it would fire louder here.
* **Every trial counts.** The ledger stands at 156 cumulative evaluations, and
  deflated Sharpe is computed against that total. Adding a foundation model is
  not one trial; it is a family of them.
* **The bottleneck is economic, not predictive.** EXP-006's best model has a
  *positive* gross Sharpe (+0.384) and a *negative* net one (−0.102), at 20.1×
  turnover. A better forecast does not fix a book that is losing to its own
  trading costs. **The next experiment worth running is turnover reduction.**

`requirements-quant.txt` already records the same decision about `torch`: "no
result so far suggests the dataset supports a sequence model."

---

## 5. QuantFrame — the open-source hedge fund stack

**What it proposes.** Four repos as four desks: Kronos (research) → skfolio
(portfolio, joined by Black-Litterman views) → NautilusTrader (execution), with
Vibe-Trading as oversight that "observes all three via MCP without authority to
trade."

### What we implemented

* **The layered contract.** Our pipeline is the same shape and is documented in
  `docs/quant.md` and `docs/training.md` as an enforced boundary rather than a
  diagram: data → point-in-time dataset → features → signal → portfolio → risk →
  cost → backtest → attribution → ledger → registry → inference → UI.
* **Research → portfolio as a typed handoff.** `/api/quant/portfolio` takes a
  model's predictions and returns weights, risk contributions and a cost
  waterfall — the signal never becomes a weight implicitly.
* **"The LLM is the analyst, not the trader."** Adopted literally and extended:
  in this repository *nothing* is the trader. The promotion gate is arithmetic in
  `ModelRegistry.promote()`, and `/api/quant/symbol/{ticker}` returns an explicit
  refusal rather than a number while production count is 0.

### What we rejected

* **The stack as assembled.** It presumes a research layer producing forecasts
  worth allocating to. Ours does not yet: alpha t +0.047, net Sharpe −0.102,
  deflated-Sharpe p 0.000 against 156 trials. Wiring Kronos → Black-Litterman →
  Nautilus on top of that would produce a complete-looking system allocating to
  noise — the exact failure this repository's architecture exists to prevent.
* **Sandbox/live parity.** Valuable, and premature without a promoted model.

The article's own closing evidence — frontier models losing 30–62% of real money
in Alpha Arena — is the best argument for the order we have chosen: establish the
edge first, build the execution stack second.

---

## 6. Qlib

*Inspected at documentation level during the EXP-007 design.*

**What it solves.** The complete research chain in one framework: data ingestion
and storage, an expression engine for factor definition, a model zoo, workflow
orchestration, experiment tracking, backtesting, portfolio construction and
nested execution.

**Architecture.** Loose-coupled modules that each work standalone. The pieces
that matter here are the **Recorder** (systematic tracking of every run's
results and metrics), **rolling retraining** with explicit handling of concept
drift, a **point-in-time database** feature specifically to prevent leakage, and
**Alpha158/Alpha360** as named, versioned feature sets rather than ad-hoc column
lists.

### What we implemented

* **Named, versioned feature sets.** Alpha158/Alpha360 are the same idea as this
  project's `FeatureArm` and the frozen `C_base` 27. Naming a feature set makes
  a result attributable to it; a study that says "all available features" cannot
  be compared to one run a month later.
* **The staged search shape.** Qlib's workflow separates screening from
  refinement rather than running one flat grid. `study/search.py`'s four stages
  are the same decomposition: Stage 1 decides where Stage 2's budget goes.
* **The Recorder discipline.** Every configuration, its hyperparameters, seed,
  dataset hash and timing land in an artifact — `search.json` and the append-only
  checkpoint. The specific thing taken is that *tracking is not optional
  instrumentation*; a run that was not recorded did not happen.

### What we rejected

* **The expression engine.** Qlib defines factors as declarative strings
  (`Ref($close, -1)/$close - 1`). It is elegant and it is the wrong trade here.
  This project's features are Python functions with a registry entry stating
  observation date, lookback, direction and a leakage test. A string DSL makes
  the *definition* compact and the **point-in-time semantics invisible** — and
  every serious defect this project has hit, including the as-of join that voided
  EXP-002, was a timing bug that a leakage test caught and a compact expression
  would have hidden.
* **The model zoo.** TabNet, TFT, HIST, KRNN and the rest are available and are
  not being added. Six studies have failed to extract a *costed* edge from this
  panel with models that fit in seconds; the constraint is the signal-to-noise
  ratio of the data, not the capacity of the estimator. Adding twelve
  architectures would add twelve hundred trials to the multiple-testing budget
  and raise the bar for everything already run.
* **Nested execution.** Optimising strategy and execution jointly is the right
  idea for a firm with a real execution stack. This project has a cost model and
  no execution venue; a nested optimiser over a cost *assumption* would be
  optimising against the assumption.

---

## 7. FinRL, FinRL-Meta, ElegantRL, FinRL-Trading

*Inspected at documentation level during the EXP-007 design.*

**What it solves.** Reinforcement learning for trading: gym-style market
environments, DRL agents (A2C, DDPG, PPO, SAC, TD3) via Stable Baselines 3,
ElegantRL or RLlib, and application layers for stock trading, portfolio
allocation and crypto.

**Architecture.** Three layers — market environments, agents, applications —
kept strictly apart, with environments under `meta/env_stock_trading`,
`meta/env_portfolio_allocation` and so on.

### What we implemented

* **Confirmation of the layer split.** FinRL's environment/agent/application
  separation is the same discipline NautilusTrader enforces and that this project
  applies as prediction / portfolio / risk / cost. Two independent references
  arriving at it moved it from "a preference" to "the load-bearing structure".
  `portfolio/optimizer.py` cannot see a model; `risk/engine.py` cannot see an
  allocator.

### What we rejected — and why RL specifically

**Reinforcement learning is not used, and the reason is not that it is hard.**

RL solves sequential decision problems where the action changes the state.
Trading has that structure — position, turnover and market impact are genuinely
path-dependent — so it is a defensible framing in general.

It is the wrong tool *here*, for three concrete reasons:

1. **There is no established edge to sequence.** Six studies say the predictive
   signal is weak and does not survive costs at 10 bp. An RL agent placed on top
   of a signal with no costed edge learns to exploit the *simulator*. The
   headline result would be a backtest, and the backtest would be of the
   environment.
2. **The trial accounting would become uncountable.** This project deflates
   Sharpe against the cumulative trial count — currently 1,035. An RL training
   run evaluates a policy thousands of times against the same folds, and every
   one of those is a look at the validation data. There is no honest number to
   put in the ledger, and "we stopped counting" is how multiple-testing bias gets
   laundered.
3. **The problem decomposes.** Prediction (what will outperform) and execution
   (how to hold it without paying the spread away) are separable here, and
   EXP-006 showed exactly which half fails: gross Sharpe +0.384, net −0.102. That
   is a turnover and cost problem with a clear, measurable objective. Wrapping it
   in a policy network makes it harder to attribute, not easier to solve.

**What would change this.** A costed edge that survives the gates, plus a
capacity constraint that makes the sizing decision genuinely path-dependent.
Neither exists yet. If EXP-007 produces the first, the second becomes worth
revisiting — as a *separate registered experiment*, with a trial-accounting
scheme designed before it runs.

---

## 8. Tooling assessed

*Assessed as components rather than studied as architectures.*

| Tool | Decision | Why |
|---|---|---|
| **XGBoost, LightGBM, CatBoost** | **Adopted**, GPU worker only | Genuine CUDA histogram paths, and three different inductive biases rather than three copies of one. Not added to the Mac environment: they are a different experiment (`EXP-007-WIN-GPU`) with their own trial count. |
| **PyTorch** | **Adopted**, GPU worker only | The one family in the GPU set that uses the device for something other than histograms. Deliberately a *small* MLP: 27 features and a low signal-to-noise target do not justify depth, and the overfitting gate would reject it. |
| **scikit-learn** | **In use** | The existing ladder. Exact-split boosting, single-threaded by the determinism rule, no CUDA path — which is why "run it on the GPU" was never an option. |
| **cvxpy** | **Declined** | `portfolio/optimizer.py` needs eight allocators and a constraint set applied to a fixed point, all of which closed-form or iterative NumPy handles. A convex-programming dependency earns its place when constraints stop being expressible that way; today it would be a dependency for an import statement. |
| **PyPortfolioOpt** | **Declined** | Overlaps skfolio, from which the estimator/optimiser split was already taken. Two portfolio libraries is one more than the problem has. |
| **mlfinlab / *Advances in Financial ML*** | **Methodology adopted, library declined** | Purging, embargo, PBO via CSCV and the deflated Sharpe ratio are all implemented here — `validation/walkforward.py` and `validation/significance.py`. The methodology is the contribution; implementing it directly means the assumptions are visible in this repository rather than behind an API. |
| **vectorbt** | **Declined** | Fast vectorised backtesting over large parameter sweeps. This project's constraint is not backtest throughput — it is that a large sweep *raises the significance bar*. A tool that makes sweeping cheaper optimises the wrong variable. |
| **backtrader, Zipline** | **Declined** | Event-driven engines for intraday and order-level simulation. Rebalances here are 5 sessions apart with a 1-period execution lag; `backtest/engine.py` covers that in a form whose cost assumptions are auditable in one file. |

---

## 9. What EXP-007 settled about these references

Recorded because a reference's value is only demonstrated when it changes an
outcome, and EXP-007 was the first study large enough to test several of them.

**mlfinlab methodology — vindicated, and it was the deciding evidence.** PBO via
CSCV and the deflated Sharpe ratio are the two statistics that rejected EXP-007,
and neither is visible in a leaderboard. A finalist cleared all eight original
gates with a deflated-Sharpe probability of 0.0485 and a PBO of 0.929. Having
implemented the methodology directly rather than through a library meant the
numbers were already computed, already in the artifact, and could be promoted to
gates the same day. **This is the single highest-value adoption in the project.**

**Qlib's staged search — adopted, and it worked as intended.** Stage 1 screened
129 configurations, 63 of them overfit, and correctly routed Stage 2's 630
configurations to the four tree families rather than spreading them across
eight. The four linear families plateaued at IC ≈ +0.005 and were dropped. A
flat grid would have spent a quarter of the search on them.

**Qlib's model zoo — rejection confirmed.** EXP-007 measured the ceiling of
eight families over 873 configurations and found the binding constraint is the
sample, not the estimator: 10.7 trials per independent block of data. Adding
TabNet, TFT and HIST would have raised the significance threshold without
touching the cause.

**skfolio's estimator/optimiser split — value now measurable, and unused.**
EXP-007's selected configuration has excess kurtosis of 43.3, which is a large
part of why its required track record is 10,545 periods against 403 available.
The portfolio layer that could address this exists and the backtest does not
call it. That gap is hypothesis H2 of `docs/EXP-008.md`, and it is a direct
consequence of having kept the layers separable.

**Vibe-Trading's refuse-don't-default — now enforced in the inference path.**
The service verifies the artifact's sha256 against its metadata, checks feature
count and ordering, and refuses to score a row that is mostly imputed. Each
failure leaves the model unloaded rather than degrading to an answer. A
prediction assembled from training medians is indistinguishable downstream from
a real one, which is exactly the failure mode the principle names.

**Kronos — rejection reinforced.** The argument for a sequence model was always
that this panel might carry temporal structure a cross-sectional model misses.
EXP-007's context sweep measured return targets against rank targets across five
feature arms: rank targets are learnable, raw return targets are not, in any
arm. A higher-capacity temporal model would be fitted to the target type that
has already been shown to carry no learnable signal here.

---

## What this repository has that none of the references emphasise

Recorded because the influence ran both ways in the design review:

* **A single-use holdout with a runtime firewall.** `assert_clear` refuses
  holdout-dated rows at every fold immediately before the fit; there is no
  environment variable that opens it.
* **Cumulative multiple-testing accounting across studies.** Deflated Sharpe is
  computed against 156 evaluations spanning five studies, not against one
  study's own count. Resetting that number when code changes is how
  multiple-testing bias is laundered.
* **Void results retained as first-class records.** EXP-002 is permanently VOID
  and still counted.
* **Promotion gated on what the evidence *says*, not only that it exists.**
  `CANDIDATE_THRESHOLDS` requires |IC t| ≥ 2, net Sharpe > 0, **gross Sharpe > 0**
  and beating the best baseline. EXP-006 clears three of four and is refused.
