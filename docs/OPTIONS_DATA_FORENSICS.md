# Options aggregates — data forensics

Date: 2026-09-19. Aggregates: `experiments/EXP-009-forensics/options.json`
(`python -m scripts.quant.data_forensics options`). Nothing after 2025-05-09 was
read. **This document does not assume options are useful.** It establishes what
exists, how it is timed, and why the family stays behind the other candidates.

## 1. What exists locally

The ~116M-row raw option-contract history is **not** on this machine. Two
derived aggregate tables are:

| Table | Rows (read through 2025-05-09) | Symbols | Range | Fields |
|---|---:|---:|---|---|
| `options_chain_daily` | 1,918,396 (1,408,144) | 2,186 | 2019-02-09 → | contracts, expirations, strikes, `atm_iv`, `put_25_iv`, `call_25_iv`, `atm_iv_near`, `atm_iv_far`, `rel_spread` |
| `options_volatility_history` | 691,007 (498,927) | 717 | 2019-05-10 → | `hv_current/week/month`, `hv_year_high/low`, `iv_current/week/month`, `iv_year_high/low` |

Both are keyed (symbol, date) with **0 duplicates** and classified `point_in_time`.

## 2. Findings

| Check | Result | Consequence |
|---|---|---|
| **Cadence** | ~3 days a week: dates fall on Mon (272), Wed (274), Fri (273) plus a few others — 941 distinct dates in 6.3 years for the chain (48 in 2019, ~155/year 2020-23, 183 in 2024) | not daily; a weekly panel sees a row within ≤ 2 sessions almost always, but 5-session-ahead alignment must be as-of, not equal |
| Symbols per date | chain ~1,520 (p10 1,504, p90 1,634); volatility history ~561 | volatility history covers only ~⅓ of the chain's names |
| **Coverage of the traded universe** | share of in-universe rows with an options row within 7 days: **chain 81.6%** (2019 86.8%, 2021 **72.8%**, 2023 83.1%, 2025 81.7%); **volatility history 69.0%** (2019: **2%**, 2020 82.4%, 2021 72.8%) | 18–31% of universe rows have no options data; the gap is not random (illiquid options → no IV) |
| Missingness inside a row | chain: `atm_iv` **31.9% null**, `atm_iv_far` **54.7%**, `atm_iv_near` 41.8%, `put_25_iv` 15.8%, `call_25_iv` 18.1%, `rel_spread` 0.05%; volatility: `iv_current` 1.6%, `iv_month_ago` 33.0%, year high/low 4.3% | skew and term-structure features exist for only ~half the rows; missing must stay missing |
| Timestamp | **date only**; the intraday time of the quotes is not recorded | see §3 |
| Look-ahead in the row | none in the row's content (`iv_year_high` etc. are backward-looking) | the risk is synchronisation, not content |

## 3. The synchronisation risk

Honarvar & Howard (SSRN 4766424; published in the *Journal of Portfolio Management* 2025 per the publisher URL) report that
options quotes recorded up to about ten minutes after the equity close create a
look-ahead when paired with the same-day stock price, and that **lagging the
options data substantially reduces the predictability found before 2008**; the
signals also weaken markedly after 2008. This dataset gives no quote time, so the
safe rule is **lag every options feature by at least one session** (attach the
latest row strictly before the panel date). Any historical "predictive" result on
same-day options data must be treated as suspect until re-run with that lag.

Two further options papers are cited in the earlier survey — Neuhierl, Tang,
Varneskov & Zhou (SSRN 3795486: few option characteristics add incremental power
once firm characteristics are controlled for) and Kelly et al. on implied-volatility
surfaces (SSRN 4531181: proprietary contract data, heavy models). **Neither was
verified in this pass** (SSRN returned HTTP 403), so neither is relied on; the
verified evidence is Honarvar & Howard above. Nothing read supports a claim that
OmniSignal's `atm_iv`/skew aggregates would help.

## 4. What is and is not reproducible

| Item | Class |
|---|---|
| IV level, IV-HV gap, IV rank, 25-delta skew, near/far term slope from these aggregates | computationally EXACT; literature **APPROXIMATED** (no contract-level surface, no delta-interpolation control, unknown quote time) |
| Risk-neutral higher moments (Ke & Wang), IV-surface CNN features (Kelly et al.) | **NOT REPRODUCIBLE** (need contract-level quotes) |
| Option volume/open-interest/put-call ratios | **NOT AVAILABLE** in the aggregates |
| Anything requiring a quote timestamp | **NOT REPRODUCIBLE** |

## 5. Verdict

**Options stay out of EXP-009.** Reasons, in order: (1) the literature evidence is
mixed and partly negative after look-ahead correction; (2) the local data are
aggregates with 18–31% coverage gaps, half-missing skew/term fields and no quote
time; (3) the family cannot be attached same-day, which erases the strongest
published effects; (4) it would confound every attribution in an experiment whose
purpose is attribution. Revisit only after a contract-level data source with quote
timestamps is licensed, and then as an isolated ablation with a one-session lag.
