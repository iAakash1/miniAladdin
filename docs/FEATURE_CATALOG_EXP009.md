# Candidate feature catalog for EXP-009

Status values: `EXISTING` means code and PIT tests already exist; `BLOCKED`
means the formula is plausible but the required historical source is absent or
unsafe. This catalog does not register or authorize an experiment.

| Feature | Family | Formula | Source | Available at | Lookback | Winsorization | Normalization | Missing handling | PIT rule | Literature source | Status |
|---|---|---|---|---|---:|---|---|---|---|---|---|
| `est_eps_rev_4w` | analyst | change in FY1 consensus / abs prior | local EPS vintages | vintage date | 20 sessions | train-fold policy only | cross-sectional rank | null on rollover/near-zero prior | backward vintage only | Chan et al.; analyst-stickiness literature | EXISTING |
| `est_eps_rev_13w` | analyst | same over 13 vintages | local EPS vintages | vintage date | 65 | same | rank | same | same | same | EXISTING |
| `est_sales_rev_4w/13w` | analyst | FY1 sales consensus change | local sales vintages | vintage date | 20/65 | same | rank | null | backward vintage only | revision literature | EXISTING |
| `est_eps_dispersion` | analyst | (high-low)/abs consensus | local EPS vintages | vintage date | 0 | same | rank | null near zero | same-day vintage | Diether et al. | EXISTING |
| `est_revision_breadth` | analyst | positive minus negative individual revisions / count | individual forecasts | each forecast timestamp | 20 | declared | rank | null below min analysts | no consensus reconstruction from future contributors | revision literature | BLOCKED |
| `earn_surprise_pct` | earnings | (reported-estimate)/abs estimate | EPS history + calendar | BMO same session; AMC/unknown next | event | same | rank | null near zero/unmatched | announcement gate | Ball & Brown; PEAD | EXISTING |
| `earn_sue` | earnings | surprise / std(prior surprises) | same | same | >=4 prior events | same | rank | null insufficient history | current surprise excluded from scale | Foster et al. | EXISTING |
| `pead_days_since` | earnings | sessions since latest available print | same | event availability | 63 cap | none | rank/decay optional only if registered | null before first event | backward event join | Bernard & Thomas | EXISTING as `earn_days_since` |
| `guidance_revision` | earnings | new minus prior guidance, scaled | timestamped 8-K/exhibit parser | filing acceptance | event | declared | rank | null absent guidance | filing version and acceptance time | Siano; event literature | BLOCKED |
| `fund_gross_profitability` | fundamental | gross profit / assets (canonical variant) | versioned SEC facts | filing acceptance | quarterly | declared | rank within industry | null absent denominator | accession version only | Novy-Marx | BLOCKED; local margin variant exists |
| `fund_accruals` | fundamental | (NI-CFO)/assets | local statements | matched announcement | quarterly | train-fold only | rank | null absent | announcement gate | Sloan | EXISTING, restatement risk |
| `fund_asset_growth_yoy` | fundamental | delta assets / prior assets | local statements | matched announcement | 4 quarters | same | rank | null gap | announcement gate | Cooper et al. | EXISTING, restatement risk |
| `fund_book_to_market` | fundamental | book equity / PIT market cap | SEC facts + PIT shares/prices | filing acceptance and market date | quarterly | same | sector rank | null missing shares | no current-share backfill | classic characteristic literature | BLOCKED |
| `opt_iv_30d` | options | interpolated 30-day ATM IV | contract quotes | quote cutoff | snapshot | bounds 1--400% | rank | null no bracket | quote time <= decision | options literature | BLOCKED; aggregate `opt_iv` exists |
| `opt_iv_rank` | options | (IV-low52)/(high52-low52) | local vol snapshots | snapshot date | source trailing year | IV validity bounds | rank | null bad span/stale | latest prior, <=21d | options literature | EXISTING |
| `opt_skew_25d` | options | (put25-call25)/ATM | local chain aggregate | snapshot date | snapshot | IV bounds | rank | null missing bucket | latest prior, <=21d | options literature | EXISTING coarse |
| `opt_term_slope` | options | far ATM / near ATM - 1 | local chain aggregate | snapshot date | snapshot | IV bounds | rank | null missing leg | same | options literature | EXISTING coarse |
| `insider_net_purchase_30d` | insider | open-market purchase value minus sale value, scaled | SEC Forms 4/5 | filing acceptance | 30d | declared | size/sector rank | explicit no-filing indicator separate from null parse | transaction and filing both prior | insider literature/SEC | BLOCKED |
| `insider_cluster_buy_30d` | insider | distinct purchasing insiders | SEC Form 4 | filing acceptance | 30d | cap only if preregistered | rank | zero only means verified no filing in complete feed | same | insider literature | BLOCKED |
| `institutional_ownership_change` | 13F | current minus prior reported ownership | SEC 13F | filing acceptance, up to 45d lag | quarterly | declared | rank | null unmatched | never period-end dated | holdings literature | BLOCKED |
| `short_interest_change` | short | PIT change in short interest | licensed exchange/vendor history | dissemination date | report interval | declared | rank | null | reporting lag honored | short-interest literature | BLOCKED |

General rule: missing analyst/options/event/fundamental values are never filled
with zero. Zero is permitted only when a complete filing feed establishes the
economic statement “no qualifying event in the lookback,” and an explicit
coverage flag accompanies it.
