# OmniSignal — Redesign Specification

July 2026. Covers: UX audit, research summary, design rationale, information architecture.

---

## 1. UX audit of the previous site

### Structural findings

**Everything was behind sign-in.** The middleware protected every route, so the product had no public surface at all: no way to learn what OmniSignal does, what the methodology is, or what Pro costs without creating an account. For a research product, this inverted the trust sequence — you were asked to commit before you were told anything.

**One page carried every job.** Marketing copy ("Agentic Multi-Factor Risk Engine"), the analysis tool, macro data, upgrade prompts, and the free-tier meter all lived in a single route. The hero re-introduced the product to signed-in users on every visit — users who had already signed in were shown a sales pitch for the thing they were using.

**The engine's best data was thrown away.** The API returns `company_name`, `sector`, `market_cap`, `pe_ratio`, `forward_pe`, `eps`, `beta`, `analyst_target`, `week_52_high/low`, and per-day `volume` — none of which were rendered. An analysis of NVIDIA never displayed the word "NVIDIA". The single most expensive thing the product does (multi-source research) was presented at a fraction of its actual depth.

**News was a footnote, not a section.** Headlines appeared only inside an analysis result, unlinked for free users, with no browsing, search, filtering, or freshness independent of a ticker query.

### Visual findings (the "AI-generated" symptoms)

The previous aesthetic accumulated most of the patterns the brief bans: a fixed dot-grid overlay on the entire viewport; an ambient radial cyan glow behind the content; glow box-shadows on card hover (`0 0 22px` accent); a display typeface (Syne) strongly associated with template/crypto sites; monospace uppercase letter-spaced text used for *everything*, including body copy; pill-shaped badge chips around the hero; a blinking "LIVE" dot; and a hero that names the product in giant type rather than saying what it does. Individually defensible; together they read as generated.

### Engineering findings

Inline style objects on nearly every element (no reusable system, inconsistent values, unthemeable); `any`-typed normalizers at the data boundary; a state-update-during-render pattern for macro loading (`if (!macroLoaded) { setMacroLoaded(true); fetch(...) }`); fonts loaded via render-blocking Google Fonts `<link>` plus a duplicate `@import` in CSS; a Tailwind v4 install that was effectively unused (three directives, zero utility classes); `middleware.ts` outside `src/` while the app lives in `src/`; no metadata beyond a title string, no sitemap, no robots, no OG image; no error boundaries; no reduced-motion handling.

---

## 2. Research summary

Sources studied for principles (not copied): Financial Times and Bloomberg for editorial density and news hierarchy; Stripe for marketing-page rhythm and restrained color; Linear for near-monochrome dark UI where color is reserved for meaning; Apple for typographic scale discipline; GitHub/Vercel for dashboard density and empty states.

Principles extracted and applied:

1. **Typography does the branding.** FT and Stripe are recognizable from a paragraph alone. A serif with real character for editorial surfaces, a neutral sans for UI, a mono reserved strictly for data. Hierarchy from weight/size/spacing, never from glow or gradient.
2. **Color is information.** In terminal-class products (Bloomberg, Linear), the UI is close to monochrome; green/red/amber are *semantic* — they mean long/short/caution — so they are never spent on decoration. One brand accent (deep emerald) used sparingly for interaction and identity.
3. **Editorial layouts are dense and asymmetric.** Premium news surfaces (FT) use one lead story with image + tight typographic rows with hairline separators — not uniform card grids of identical rounded rectangles (the template look).
4. **Live data is the best marketing.** Stripe shows real API responses on its homepage. OmniSignal's landing shows the *actual* macro readout from FRED and *actual* headlines from the news pipeline — proof over promises.
5. **Trust products explain themselves.** Bloomberg-adjacent products win by showing their working. The methodology — the exact five factors, their point weights, the SRM dampening — is published on the landing page, verbatim from the engine.
6. **Verified data plumbing.** Live checks performed during research: Railway API healthy (`/api/health` — all five sources up); `/api/macro` shape captured (`risk_multiplier` + `stats{}` with percent-strings); `/api/research/NVDA` full shape captured including the unused fundamentals; Yahoo Finance RSS (`finance.yahoo.com/news/rssindex`) and Dow Jones/MarketWatch feeds (`feeds.content.dowjones.io/public/rss/*`) confirmed live; CNBC feeds treated as optional (aggregator degrades gracefully per-feed).

---

## 3. Design rationale

### Two rooms, one house

The product gets two deliberately different atmospheres sharing one skeleton (identical spacing scale, radii, type families, semantic colors):

- **Public site — editorial light.** Warm paper (`#FAF9F6`), near-black warm ink, a deep emerald accent, Newsreader serif for display. It reads like a research publication: the correct register for "trust us with your investing decisions."
- **Terminal — refined dark.** Warm charcoal (`#111210`), hairline borders instead of shadows, near-monochrome chrome, mono reserved for figures, semantic green/red/amber only where they carry meaning. No dot grid, no glow, no glass. It reads like an instrument.

The contrast is intentional: marketing invites, the terminal concentrates. The shared skeleton keeps them siblings rather than strangers.

### Type system

- **Newsreader** (serif, optical sizing) — display and editorial headings on the public site. Chosen for its text-face credibility at large sizes; it is not a "startup font."
- **Inter** — all UI, body, labels. Tabular figures enabled where numbers align.
- **IBM Plex Mono** — tickers, prices, scores, table figures. *Only* data. The previous site's all-mono body text was the single largest generated-feel contributor.

Scale (both themes): 12 / 13 / 14 / 16 / 18 / 22 / 28 / 36 / 52-76(clamp). Line heights: 1.15 display, 1.45 UI, 1.7 reading. Labels: 11px, +0.08em, uppercase, used sparingly.

### Color

Light: paper `#FAF9F6`, surface `#FFFFFF`, ink `#1C1B18` (15.4:1 on paper), secondary `#5B594F` (7:1), hairline `#E8E6DE`, accent emerald `#1E6B54` (5.6:1).
Dark: bg `#111210`, panel `#181917`, text `#EAE8E1` (14.9:1), muted `#A3A198` (7.2:1), hairline `rgba(255,255,255,.08)`, accent `#43B183`.
Semantic (both): positive `#177749`/`#3FB984`, negative `#B3382E`/`#E0564F`, caution `#96690F`/`#D9A13C`. All AA at their usage sizes; most AAA.

### Motion

150–250ms, ease-out, opacity + ≤8px translate only. One scroll-reveal primitive on marketing (IntersectionObserver, fires once). No infinite animations except a 2s soft pulse on the live-data dot. Everything gated behind `prefers-reduced-motion`.

### Copy

Voice: a research desk, not a startup. Specific numbers over adjectives ("Five weighted signals, one risk-adjusted verdict", "₹50/month", "RSI-14 below 30 adds +2"). Banned and removed: "agentic," "AI-powered," "your edge," "revolutionary," rocket-ship framing. The disclaimer (research/education, not advice) is presented plainly, not buried.

---

## 4. Information architecture

```
Public (light, no auth)
├── /                 Landing: what it is → live macro proof → methodology
│                     (5 factors + weights + SRM) → product preview →
│                     live news preview → pricing → FAQ → footer
├── /news             Live market news: lead story + editorial list,
│                     category tabs, search, pagination
├── /sign-in, /sign-up  Clerk, restyled to the editorial language
└── /api/news, /api/macro   public data endpoints (news aggregation is ours;
                            macro proxies Railway)

Authenticated (dark)
└── /terminal         The instrument. Command bar → company header band →
                      chart + key stats → fundamentals / macro / sentiment →
                      headlines. Free-tier meter, Pro gating, Razorpay intact.
                      /api/research, /api/chart, /payment/* remain protected.
```

Navigation is honest about the boundary: the public site's single CTA is "Open terminal" (→ sign-in when signed out); the terminal links back only in its footer. Signed-in users landing on `/` see the header CTA switch to "Open terminal" — no forced redirect; the marketing site remains readable.

### What was deliberately not built

A separate /pricing page (one plan — a section with an anchor is honest; a page would be padding); a blog; testimonials (none exist — fabricating them is exactly the template smell this redesign removes); social-proof logos (same reason).
