# Replication candidate: point-in-time SEC filing text

| Item | Assessment |
|---|---|
| Original papers | Celeny et al., [*Cyber Risk and the Cross-Section of Stock Returns*](https://arxiv.org/abs/2402.04775); Siano, [*News in Earnings Announcement Disclosures*](https://doi.org/10.1287/mnsc.2024.05417) |
| Original data | Celeny: 60,470 SEC 10-Ks for 7,059 CRSP/Compustat firms, 2007–2022, plus MITRE ATT&CK. Siano: earnings press-release disclosures; full text paywalled |
| Original target/model | Celeny creates a document score using doc2vec DM/DBOW trained on >1.7m paragraphs and MITRE descriptions; Siano uses LLM-derived disclosure news for short-window returns |
| Original validation | Celeny assigns the most recent 10-K score and rebalances quarterly into value-weight quintiles, 2009–2022; Siano compares text measures around announcements |
| Original result | Celeny reports positive high-minus-low cyber-risk returns; Siano's abstract reports substantially greater explanatory power than dictionary measures. Neither is direct evidence for a 21-day liquid-250 selector net of costs |
| Original compute | Not reported in the papers reviewed |
| What we have | Open-SEC access path, a 21-session event target and portfolio/cost machinery |
| What we lack | Accepted-at filing corpus, exhibit/document identity, CIK master, historical firm mapping and frozen text embeddings |
| Feasible substitute | Start with numeric filing novelty and TF-IDF/doc2vec or frozen domain embeddings; compare against numeric surprise and filing-change baselines |
| MacBook plan | Download/parse/validate documents; CPU baselines. First frozen-embedding pass estimated 8–30 h |
| Kaggle plan | Shard accepted-at documents across two independent T4s; estimated 2–8 h first pass, 6–12 GB VRAM each |
| Data preparation time | 1–3 weeks after security-master basics; event-time hand audit is mandatory |
| Implementation complexity | MEDIUM–HIGH |
| Leakage risk | Amended filings, exhibit-versus-filing timestamps, after-close acceptance, document duplicates and using later-restated text |
| Licensing risk | SEC and MITRE are public subject to their terms/fair-access rules; CRSP/Compustat exact return panel is licensed; Siano details are partially inaccessible |
| Recommendation | **ADAPT LATER**, after numeric SEC facts and identity are reliable |

Text is a distinct information family and therefore more defensible than a
bigger price-only network. It is still second to as-reported numeric facts:
timestamp and identity errors are easier to detect in structured XBRL than in
document corpora.
