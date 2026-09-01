# Terminal reference study

What was studied while building the OmniSignal terminal, what was adopted, and
what was deliberately not.

**Licensing, first, because it constrains everything else.** Both primary
references are **AGPL-3.0**. Fincept additionally dual-licenses, with the open
repository carrying explicit restrictions on commercial, internal and hosted
use. AGPL's copyleft reaches network use: incorporating their code would oblige
this repository to publish under the same terms.

**No code, markup, styling or assets from either project appear here.** What
follows is a study of architecture and product patterns, implemented
independently. Neither project is affiliated with this one, and no compatibility
or endorsement is claimed.

---

## 1. Fincept Terminal

<https://github.com/Fincept-Corporation/FinceptTerminal> · AGPL-3.0-or-later,
dual-licensed

**What it is.** A desktop financial terminal organised into desks — agentic
research, quant lab and backtesting, fundamental research, markets and
execution, macro intelligence, and a custom workspace. It ships 100+ data
connectors (FRED, IMF, World Bank, DBnomics, Polygon, Yahoo, government APIs)
and a large set of LLM agents across multiple providers, plus a visual node
editor for workflow composition.

### Adopted

**Desks, not pages.** The strongest idea here. Fincept groups by *what you are
doing* rather than by which data source is involved. Our navigation was a flat
list of seven features in which the deepest surface in the product — the quant
research workspace, holding the experiment register, the search lab, the
promotion gates and the holdout firewall — **had no entry at all** and was
reachable only by typing the URL.

The navigation is now ordered as a research workflow: Market → Research →
Factors → **Quant** → Models → Portfolio → Workspace → Learn. Validation and
Methodology moved out of Learn, where filing them had told the reader that the
evidence behind the research was optional reading.

**Command-first addressing of sections, not just pages.** Researchers arrive
with a specific question — *did it clear the gates*, *what is the holdout
doing*, *what command runs this*. The palette now answers those directly with
deep links (`/quant#verdict`, `/quant#provenance`, `/quant#run`) instead of
depositing the reader at the top of a long page to scroll.

**Density as a signal of seriousness.** Adopted in the `.qt` research surface:
hairline borders, corners off, tabular monospace numerics, no card shadows.

### Rejected

**The node editor.** Visual workflow composition is compelling and solves a
problem we do not have. Our research pipeline is a small number of
pre-registered experiments whose entire value depends on being *fixed* before
they run. A UI for recombining research steps is a UI for generating
uncounted trials, and this project's binding constraint is already that it has
spent 1,029 of them on ~96 independent blocks of data.

**37 agents.** Breadth of persona is not breadth of evidence. One assistant
grounded in real artifacts is worth more here than many that can each be asked
for an opinion.

**100+ connectors as a goal.** EXP-005 and EXP-007's context sweep both measured
that adding data sources to this panel *reduces* information — the arm with
every source (`G_all`, IC +0.0096) is the worst base-containing arm. Connector
count would be a vanity metric against our own evidence.

---

## 2. OpenBB

<https://github.com/OpenBB-finance/OpenBB> · AGPLv3

**What it is.** A data platform whose stated shape is "connect once, consume
everywhere": a provider abstraction over many sources, standardised data models,
extensions and routers, an auto-generated FastAPI REST layer, and surfaces for
Python, Excel, a workspace UI, and MCP servers for AI agents.

### Adopted

**Provider → normalised model → service → API → widget.** The layering
principle, applied where it earns its place rather than as a rewrite. The
concrete adoption is the **widget contract**: `components/terminal/primitives`
now defines `Panel`, `Metric`, `StateBlock` and `ProvenanceChain`, and `Panel`
carries `source`, `asOf`, `retrievedAt` and `status` *in the container*.

That last detail is the whole point. Before it, each workspace invented its own
shape for "a number with some context", and each decided independently whether
to show a methodology or an as-of date. Making provenance part of the container
means a panel cannot be built without deciding what it says about where its
numbers came from. `Metric` takes `method` for the same reason: a Sharpe without
its cost assumption and a VaR without its estimator are both unfalsifiable, and
a component that makes omission easy will have it omitted.

**Standardised responses over provider-shaped ones.** `quant_search_service`
serves one shape whether a search is running (read from the append-only
checkpoint) or complete (read from the artifact), with `state` naming which. The
UI does not branch on file layout.

**Derivations labelled as derivations.** The selection read layer now restates a
recorded verdict against the gate standard in force today, returning it as
`current_standard` beside the untouched recorded `verdict`. Nothing is refit and
the artifact is not modified — an eight-gate artifact that carries a
deflated-Sharpe probability of 0.06 and a PBO of 0.93 in the same file was
telling the reader two different things, and they are entitled to know which
standard applies.

### Rejected

**Auto-generated REST from a provider registry.** Real value at OpenBB's
provider count; overhead at ours. Our quant endpoints are hand-written, short,
and lazy-import the research package so the minimal inference runtime does not
pay for it.

**A general widget-composition workspace.** User-arranged dashboards make sense
when widgets are interchangeable views of comparable data. Here the ordering
*is* the argument: the research page leads with what is blocked and sealed and
then shows supporting statistics, and a layout that let a reader move net Sharpe
below the fold would let them build a page that misrepresents the research.

**Excel and MCP surfaces.** Nothing here is stable enough to be worth consuming
from three more places.

---

## 3. Quant references, in brief

Full treatment in [quant-references.md](quant-references.md); summarised here so
this document stands alone.

| Reference | Status | Substance |
|---|---|---|
| **mlfinlab methodology** | Adopted, decisive | PBO via CSCV and the Deflated Sharpe Ratio are the two statistics that rejected EXP-007, and both are now promotion gates. The highest-value adoption in the project. |
| **skfolio** | Adopted | Estimator/optimiser separation. `portfolio/optimizer.py` cannot see a model; a covariance bug is distinguishable from an allocation bug. |
| **NautilusTrader** | Adopted | Layer separation and deterministic clocks. Signal / portfolio / risk / cost stay apart. |
| **Vibe-Trading** | Adopted, now enforced | Refuse-don't-default. Inference verifies the artifact's sha256, feature count and feature order, and refuses a row that is mostly imputed — each failure leaves the model unloaded rather than degrading to an answer. |
| **Qlib** | Partly adopted | Staged search and the Recorder discipline. Expression engine and model zoo rejected. |
| **FinRL family** | Layer split confirmed; RL rejected | No costed edge to sequence, uncountable trials, and EXP-006 already localised the failure to turnover. |
| **Kronos** | Rejected | EXP-007's context sweep measured rank targets as learnable and raw return targets as not, in every arm. A higher-capacity temporal model would be fitted to the target type already shown to carry no learnable signal. |

---

## 4. What none of the references gave us

Recorded because the influence ran both ways.

- **A single-use holdout with a runtime firewall.** `assert_clear` runs on both
  frames of every fold before every fit, and setting
  `QUANT_DISABLE_HOLDOUT_FIREWALL` makes the firewall raise rather than lift.
- **Cumulative multiple-testing accounting across studies.** 1,029 trials
  spanning six studies, not one study's own count.
- **A UI whose ordering is chosen against the product's interest.** The research
  page leads with the gates a model failed and shows its strong statistics
  afterwards. Neither reference has a reason to solve this; neither of them is
  presenting a model of their own that they would rather flatter.
