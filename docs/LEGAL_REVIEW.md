# Legal pages and provider licensing: audit and open questions

State on 2026-10-25, branch `feat/legal-and-provider-console`. This records what
was found, what was changed, what was verified and against which source, and
what still needs the owner or a lawyer. It is a working record, not legal
advice, and nothing in it is a claim of compliance.

## What was found

| Finding | Where | Resolution |
|---|---|---|
| No Terms page and no Privacy page existed; the footer linked to neither | `dashboard/src/app`, `SiteFooter.tsx` | `/terms` and `/privacy` added, public, in the sitemap, linked from the footer and the sign-in screen |
| FRED's API terms require public applications to show a fixed notice and link to the terms; the site showed neither | footer | Notice added verbatim to the footer and the Terms; held equal to the backend catalog by a test |
| The SEC and Wikidata User-Agents named `research@omnisignal.app`, a mailbox no one has shown to exist | `sec_vendor.py`, `wikidata_vendor.py` | Wikidata now sends the repository URL (accepted, HTTP 200, 2026-10-24). SEC rejects an identifier without an email (HTTP 403 to a URL-only one, 2026-10-24), so its fallback is unchanged and the providers page raises an advisory until `SEC_USER_AGENT` is set |
| Library errors were recorded without redaction, so a library that puts the key in its URL could surface it | `base.timed_call` | Redacted like HTTP errors; tested |
| Vendor names were a hard-coded table in the page; health counted any failure ever as "degraded" for the life of the process; there was no stale or disabled state and no recent-activity record | providers page, `base.py` | Server-side catalog and registry view; windowed health with `STALE`/`DISABLED`; per-vendor recent calls (operations only); see `docs/PROVIDERS.md` |

## What the pages state, and how each claim was checked

| Claim | Checked against |
|---|---|
| Independent, experimental project of its owner; source at github.com/iAakash1/miniAladdin | the public repository |
| Not a bank, broker or adviser; does not execute trades; paper trading is simulated | `src/broker/alpaca_paper.py` can reach only `paper-api.alpaca.markets` |
| Signals come from a deterministic engine; AI models write explanations only | scoring and narrative pipeline (`src/scoring`, `src/services/narrative_pipeline.py`) |
| Earlier versions shipped with the MIT License | commit `2fee22c` ("remove unused MIT license") |
| Sign-in by Clerk; saved research keyed to the Clerk id | `src/services/clerk_auth.py`, `supabase/migrations/*` (profiles, watchlists, analysis_history, saved_reports, portfolio_positions, user_preferences, research_sessions, session_notes) |
| Pro is a one-time payment through Razorpay; order and payment ids kept in account metadata; no card data held | `dashboard/src/app/payment/verify/route.ts`, `UpgradeDialog.tsx` |
| Request logs: id, method, path, status, duration, Clerk id when signed in | `request_logging` middleware in `api/index.py` |
| Browser storage: theme, display, free-run count, recent items | `localStorage` keys in `dashboard/src/lib/*` |
| Typed questions go to AI model providers (DeepSeek, Groq) | `/api/ask` → `ask_service`; `llm_service.py` reads `DEEPSEEK_*`, `GROQ_*` |
| No advertising or third-party analytics trackers | `dashboard/package.json` (no analytics package); CSP `connect-src` lists only Clerk and Razorpay |
| The database answers only the backend | row-level security enabled on all nine tables with no policy for browser roles; no database client or key in `dashboard/src` |
| Deleting the Clerk account does not delete saved research | no `user.deleted` webhook or cleanup exists |

## Needs a lawyer or an owner decision

1. **Regulatory status of paid signals.** OmniSignal shows Buy/Hold/Sell labels and sells one-time Pro access (₹100). Under the SEBI (Research Analysts) Regulations, 2014, as amended in December 2024, a research analyst is a person who, *for consideration*, is engaged in the business of providing research services; buy/sell recommendations are research-analyst territory. Whether a paid, automated signal service falls inside that definition, or inside US adviser rules for US users, is not something these pages can settle. The disclaimers do not exempt the service from any obligation. **Get advice before charging for access in production.**
2. **Personal-data law.** India's Digital Personal Data Protection Rules, 2025 were notified on 13 November 2025; the core notice, consent and breach obligations apply from 13 May 2027 (verify against the Gazette, G.S.R. 846(E)). Users elsewhere bring other regimes. The privacy notice is written from the code, not as a statement of compliance.
3. **Governing law and disputes.** Deliberately omitted. Choose a jurisdiction (or none) with advice.
4. **A private contact channel.** The pages point to public GitHub issues because that is the only published channel. Data requests, intellectual-property complaints and security reports need a private address. The account email was not used: it is reserved for Git authorship.
5. **Refunds and cancellation for Pro.** No policy exists, and none was invented. Payment processors and consumer law may require one.
6. **Liability wording.** The "as is" and limitation clause is bounded by "to the extent permitted by law" and preserves non-waivable consumer rights; there is no cap amount and no indemnity. Review before relying on it.
7. **Age.** No minimum age is stated. Decide whether one is needed.
8. **Effective date.** `LEGAL_LAST_UPDATED` (`dashboard/src/lib/legal.ts`) is 2026-10-25, the date the wording was written. If the pages ship later with no wording change, the date stays; change it whenever the wording changes.

## Provider licensing

Three providers have terms, read on 2026-10-24, that restrict how this
deployment uses them. The registry marks them for review, and
`PROVIDER_DISABLED` can take any of them out of routing without removing the key:

- **Finnhub:** plans are personal-use unless stated; showing its data or results derived from it to other users needs written approval.
- **NewsAPI:** the free Developer plan may not run in production.
- **Yahoo Finance via yfinance:** an unofficial library; its README says Yahoo's API is for personal use only.

Also read: **FRED** requires the notice (now shown) and permission for third-party copyrighted series beyond personal use. **SEC EDGAR** requires at most 10 requests/s (the adapter allows 60/min) and a User-Agent with a contact. **Massive** separates individual and business terms; the business terms were not read.

"Located, not reviewed" means the terms page exists at that address but its
contents have not been read. "Not located" means no page was found at the
address tried; the terms still apply. Neither is a permission.

| Provider | Domain | Kind | Credential | Terms | Restrictions read, or open question |
|---|---|---|---|---|---|
| Alpha Vantage (`alpha_vantage`) | fundamentals | commercial | `ALPHA_VANTAGE_KEY` | [Located, not reviewed](https://www.alphavantage.co/terms_of_service/) | Not reviewed; permitted use unverified. |
| Apify (`apify`) | knowledge | platform | `APIFY_API_TOKEN` | [Located, not reviewed](https://docs.apify.com/legal/general-terms-and-conditions) | Runs third-party scrapers; the terms of each scraped site apply in addition to Apify's. |
| ClinicalTrials.gov (`clinicaltrials`) | official_record | government | `none (keyless)` | [Located, not reviewed](https://clinicaltrials.gov/about-site/terms-conditions) | Not reviewed; permitted use unverified. |
| ECB Data Portal (`ecb`) | macro | intergovernmental | `none (keyless)` | Not located | Not reviewed; permitted use unverified. |
| Exa (`exa`) | search | commercial | `EXA_API_KEY` | [Located, not reviewed](https://exa.ai/terms) | Not reviewed; permitted use unverified. |
| Federal Register (`federal_register`) | official_record | government | `none (keyless)` | [Located, not reviewed](https://www.federalregister.gov/developers/documentation/api/v1) | Not reviewed; permitted use unverified. |
| Financial Modeling Prep (`fmp`) | fundamentals | commercial | `FMP_API_KEY` | [Located, not reviewed](https://site.financialmodelingprep.com/terms-of-service) | Not reviewed; permitted use unverified. |
| Finnhub (`finnhub`) | market_data | commercial | `FINNHUB_API_KEY` | [Reviewed](https://finnhub.io/terms-of-service) | **Owner decision needed.** Plans are for personal use unless stated otherwise. Redistributing or sharing the data, or results derived from it, needs Finnhub's written approval. Data must be deleted when the subscription ends. Showing Finnhub-derived values to other users needs that approval. |
| FRED (St. Louis Fed) (`fred`) | macro | government | `FRED_API_KEY` | [Reviewed](https://fred.stlouisfed.org/docs/api/terms_of_use.html) | Public applications must show the not-endorsed notice and link to these terms. Some series are copyrighted by third parties and need the owner's permission beyond personal use; those series carry a copyright note in FRED. |
| GNews (`gnews`) | news | commercial | `GNEWS_API_KEY` | Not located | Not reviewed; permitted use unverified. |
| Logo.dev (`logo_dev`) | visual | commercial | `LOGO_DEV_PUBLISHABLE_KEY` | Not located | Not reviewed; permitted use unverified. |
| Marketaux (`marketaux`) | news | commercial | `MARKETAUX_API_KEY` | Not located | Not reviewed; permitted use unverified. |
| Marketstack (`marketstack`) | market_data | commercial | `MARKETSTACK_API_KEY` | [Located, not reviewed](https://marketstack.com/terms) | Not reviewed; permitted use unverified. |
| Massive (`massive`) | market_data | commercial | `MASSIVE_API_KEY` | [Reviewed](https://massive.com/terms) | Index page only: products labelled Individual Use are for personal, non-business use; business use falls under separate Business terms, which were not reviewed. Display and redistribution limits are in those terms. |
| NewsAPI (`newsapi`) | news | commercial | `NEWSAPI_KEY` | [Reviewed](https://newsapi.org/terms) | **Owner decision needed.** The free Developer plan is for development only and may not run in staging or production; a paid plan is required there. Copyrighted articles may not be republished. |
| openFDA (`openfda`) | official_record | government | `OPENFDA_API_KEY` | [Located, not reviewed](https://open.fda.gov/terms/) | Not reviewed; permitted use unverified. |
| OpenFIGI (`openfigi`) | identity | commercial | `OPENFIGI_API_KEY` | [Located, not reviewed](https://www.openfigi.com/docs/terms-of-service) | Not reviewed; permitted use unverified. |
| Polygon.io (`polygon`) | market_data | commercial | `POLYGON_API_KEY` | [Located, not reviewed](https://polygon.io/terms) | Massive serves the same Polygon wire format; whether the two share terms was not checked. |
| SEC EDGAR (`sec`) | filings | government | `none (keyless)` | [Reviewed](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) | Fair-access policy: at most 10 requests per second, and every request declares a User-Agent naming the requester and a contact address. |
| Tavily (`tavily`) | search | commercial | `TAVILY_API_KEY` | [Located, not reviewed](https://tavily.com/terms) | Not reviewed; permitted use unverified. |
| Tiingo (`tiingo`) | market_data | commercial | `TIINGO_API_KEY` | Not located | Not reviewed; permitted use unverified. |
| Twelve Data (`twelvedata`) | market_data | commercial | `TWELVEDATA_API_KEY` | [Located, not reviewed](https://twelvedata.com/terms) | Not reviewed; permitted use unverified. |
| U.S. Bureau of Economic Analysis (`bea`) | macro | government | `BEA_API_KEY` | [Located, not reviewed](https://apps.bea.gov/API/signup/) | Not reviewed; permitted use unverified. |
| U.S. Bureau of Labor Statistics (`bls`) | macro | government | `none (keyless)` | Not located | Not reviewed; permitted use unverified. |
| U.S. Energy Information Administration (`eia`) | macro | government | `EIA_API_KEY` | [Located, not reviewed](https://www.eia.gov/about/copyrights_reuse.php) | Not reviewed; permitted use unverified. |
| U.S. Treasury Fiscal Data (`treasury_fiscal`) | macro | government | `none (keyless)` | Not located | Not reviewed; permitted use unverified. |
| Wikidata (`wikidata`) | knowledge | open_data | `none (keyless)` | [Located, not reviewed](https://www.wikidata.org/wiki/Wikidata:Licensing) | Not reviewed; permitted use unverified. |
| World Bank Open Data (`world_bank`) | macro | intergovernmental | `none (keyless)` | [Located, not reviewed](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) | Not reviewed; permitted use unverified. |
| Yahoo Finance (yfinance) (`yfinance`) | market_data | unofficial | `none (keyless)` | [Reviewed](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) | **Owner decision needed.** yfinance is not affiliated with or endorsed by Yahoo, and its README states that Yahoo's finance API is intended for personal use only. Use in a public or paid service is an open licensing question for the owner. |
| Yahoo Finance RSS (`yahoo_rss`) | news | commercial | `none (keyless)` | [Located, not reviewed](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) | Not reviewed; permitted use unverified. |

Generated from `src/providers/catalog.py`; regenerate it when the catalog changes.
