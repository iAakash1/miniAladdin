# OpenBB — architecture study

Sources: <https://github.com/OpenBB-finance/OpenBB> (platform, provider layer,
`openbb_platform/core/openbb_core/provider/standard_models`) and
<https://github.com/OpenBB-finance/widgets-library>.

**Licence: AGPLv3.** Copyleft reaches network use. **No OpenBB code, schema
files, assets or branding appears in this repository**, and no affiliation is
claimed. What follows is a study of architecture, implemented independently.

---

## What OpenBB does that is worth taking

### 1. Standard models: `QueryParams` + `Data`, extended by providers

~200 files under `standard_models/` — `equity_historical.py`,
`balance_sheet.py`, `economic_indicators.py` and so on. Each declares a
**QueryParams** class (standardised inputs) and a **Data** class (standardised
output). Provider implementations *extend* these, adding vendor fields while
keeping the core contract.

**Why it works.** Consumers code against one shape, so providers stay swappable
and a provider's response format never reaches a component. The abstraction is
what makes "connect once, consume everywhere" true rather than aspirational.

**Adopted, at our scale.** `src/services/envelope.py::DataEnvelope` is the same
move: one shape for every served value, domain payload inside. We have far fewer
domains than OpenBB and did not need 200 model files — what we needed was that
*a value and its provenance travel together*.

**Rejected: the full 200-model taxonomy and provider-routing layer.** Real value
at OpenBB's provider count; pure overhead at ours. Our quant endpoints are
hand-written, short, and lazy-import the research package so the minimal
inference runtime does not pay for it.

### 2. The widget contract

`widgets.json` registers each widget with `widgetId`, `name`, `description`,
`category`, `searchCategory`, `gridData` (`w`, `h`, `minW`) and a `source`
array.

**Why it works.** Provenance and identity are *declared alongside the widget*
rather than living in documentation, so a widget cannot exist without saying
what it is and where its data comes from.

**Adopted, tightened.** `components/terminal/primitives/Panel` takes `source`,
`asOf`, `retrievedAt` and `status` **in the container**. A panel cannot be built
without deciding what it says about its data's origin. `Metric` requires a
`method` for the same reason: a Sharpe without its cost assumption and a VaR
without its estimator are both unfalsifiable, and a component that makes
omission easy will have it omitted.

`EnvelopeMetric` closes the loop — it renders straight from a server envelope,
so the methodology text lives in one place instead of being restated in every
component that happens to show the same number. It previously *had* drifted
between two components showing net Sharpe.

**Rejected: `gridData` and user-arranged dashboards.** See the Fincept study —
on a research page the ordering is the argument.

### 3. Status as a first-class field

**Adopted and hardened past the reference.** Our `Status` enum distinguishes six
states — `live`, `stale`, `recorded`, `waking`, `unavailable`, `unknown` — and
`status` is **computed** from the timestamp and the declared policy. A caller
cannot label stale data live, because a caller does not get to label anything.

Two distinctions we found we needed and that a generic terminal has less reason
to draw:

- **`recorded` is not `stale`.** An experiment artifact from August is dated,
  not decaying. A ttl-less policy returns `recorded` regardless of age, because
  "may I trust this as current?" is not a question that applies to an artifact.
- **`waking` is not `unavailable`.** Render's free tier takes ~43s to wake
  against an 8s request budget, so a timeout is the *expected* first response
  after a quiet period. One means retry; the other means stop waiting.

### 4. Auto-generated REST from the provider registry

**Rejected.** Worth it at OpenBB's surface area. Ours is a dozen endpoints whose
value is that each one is short enough to read.

---

## What we have that neither reference emphasises

Recorded because the influence ran both ways.

- **A single-use holdout with a runtime firewall.** `assert_clear` runs on both
  frames of every fold before every fit, and `QUANT_DISABLE_HOLDOUT_FIREWALL`
  makes the firewall *raise* rather than lift.
- **Cumulative multiple-testing accounting across studies** — 1,029 trials over
  six studies, not one study's own count.
- **A UI ordered against the product's own interest.** The research page leads
  with the gates a model failed. Neither reference has a reason to solve this;
  neither is presenting a model of its own it would rather flatter.

---

## Summary

OpenBB's transferable core is **the value and its provenance are one object**,
and the widget contract is what enforces it. Both are implemented. The provider
taxonomy that makes OpenBB powerful is the part we correctly do not need.
