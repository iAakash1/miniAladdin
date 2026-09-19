# Research data-edge matrix

`CORE` means central to the reported design, `SUPPORTING` means present as a
control/context input, and `NOT USED` means the paper's reviewed public record
does not use it. `UNVERIFIED` is retained where the primary record inspected
did not expose enough detail.

| Study | PRICE | VOLUME | FUNDAMENTALS | ANALYST | EARNINGS | OPTIONS | INSIDER | 13F | SHORT_INTEREST | NEWS | SEC_TEXT | TRANSCRIPTS | MACRO | GRAPH | ALTERNATIVE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gu, Kelly & Xiu (2020) | CORE | CORE | CORE | NOT USED | SUPPORTING | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Chen, Hanauer & Kalsbach (2024/26) | CORE | CORE | CORE | SUPPORTING via anomaly library | SUPPORTING | NOT USED | SUPPORTING via anomaly library | SUPPORTING | SUPPORTING | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Han, He, Rapach & Zhou (2024) | CORE | CORE | CORE | SUPPORTING | SUPPORTING | NOT USED | SUPPORTING | SUPPORTING | SUPPORTING | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Cakici & Zaremba (2026) | CORE | SUPPORTING | CORE | UNVERIFIED | UNVERIFIED | NOT USED | UNVERIFIED | UNVERIFIED | UNVERIFIED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Zhang, Wu & Chen LTR (2021) | CORE | SUPPORTING | CORE | UNVERIFIED | UNVERIFIED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED |
| Poh et al. LTR (2020) | CORE | SUPPORTING | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED |
| Barunik, Hronec & Tobek (2024/25) | CORE | CORE | CORE | CORE | SUPPORTING | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Analyst Stickiness (2026) | SUPPORTING | NOT USED | SUPPORTING | CORE | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Campbell et al. Expectations Matter (2024) | SUPPORTING | NOT USED | CORE | CORE | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Siano (2025) | SUPPORTING | NOT USED | CORE | NOT USED | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | CORE | NOT USED | NOT USED | NOT USED | NOT USED |
| He & Zhang (2025) | SUPPORTING | NOT USED | SUPPORTING | SUPPORTING | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | CORE | NOT USED | CORE | NOT USED |
| Honarvar & Howard (2024/25) | CORE | SUPPORTING | SUPPORTING | NOT USED | NOT USED | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED |
| Neuhierl et al. (2024 revision) | CORE | SUPPORTING | CORE | NOT USED | NOT USED | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Kelly et al. IV Surfaces (2026 rev.) | CORE | SUPPORTING | SUPPORTING | NOT USED | NOT USED | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Avramov et al. Dual Industry | CORE | SUPPORTING | CORE | NOT USED | SUPPORTING | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | CORE | NOT USED |
| Qian et al. MDGNN | CORE | CORE | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED | NOT USED | CORE | NOT USED |
| Jensen et al. Implementable Frontier | CORE | CORE | CORE | SUPPORTING | SUPPORTING | SUPPORTING | SUPPORTING | SUPPORTING | SUPPORTING | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |
| Bianchi & Zheng (2026) | CORE | SUPPORTING | CORE | SUPPORTING | SUPPORTING | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | NOT USED | SUPPORTING | NOT USED | NOT USED |

## Repeated patterns

- Price/liquidity and accounting characteristics are the most recurrent core.
- Analyst/earnings data repeatedly appear in strong incremental-information
  questions, but usually through licensed PIT histories.
- Options drive a specialized cluster, not the broad best-performing stock-
  selection literature, and recent evidence is mixed after synchronization.
- Graph and text results depend on relation/transcript/filing datasets more than
  on a universally superior model.
- Insider, 13F and short-interest evidence did not recur across the strongest
  ML papers reviewed; they remain candidate features, not foundations.
