# OmniSignal design system

One skeleton, two atmospheres. Every token lives in `dashboard/src/app/globals.css`;
the dark theme is a single class (`.theme-dark`) that overrides custom properties,
so every component is automatically bi-thematic.

---

## Foundations

### Type

| Role | Family | Usage |
|---|---|---|
| `--font-serif` | Newsreader Variable (+ italic axis) | Display headlines, section titles, news headlines. Public site only. |
| `--font-sans` | Inter Variable | All UI, body copy, labels. |
| `--font-mono` | IBM Plex Mono 400/500/600 | Data only: tickers, prices, scores, table figures. Never body text. |

Self-hosted via `@fontsource` packages (imported once in the root layout) — no
external font CSS, no render-blocking request, no layout shift.

Classes: `.display` (clamp 2.5→4.5rem serif), `.h-section` (serif section title),
`.h-panel` (16px/600 panel title), `.lede`, `.body-copy` (62ch max), `.eyebrow`
(11px caps, accent), `.label` (11px caps, faint), `.mono`, `.num` (mono + tabular
figures — use for every number that may sit above another number).

### Color

Light (default, public site): paper `#faf9f6`, surface `#ffffff`, ink `#1c1b18`,
secondary `#5b594f`, hairlines `#e8e6de`, accent emerald `#1e6b54`.

Dark (`.theme-dark`, terminal): bg `#111210`, panel `#181917`, text `#eae8e1`,
muted `#a3a198`, hairlines `rgba(255,255,255,.08)`, accent `#43b183`.

Semantic — the only place vivid color is allowed:
`--pos` (long/up), `--neg` (short/down), `--warn` (hold/caution), each with a
`-wash` background tint. Rule: color states a fact about data; it never decorates.
All pairings meet WCAG AA at their used sizes; body text exceeds AAA.

### Space, radius, elevation

4px base grid; marketing sections breathe at `clamp(64px, 9vw, 112px)`; panel
padding 20–26px; data rows 9–13px vertical. Radii: 4 / 6 / 10px (`--r-sm/md/lg`)
— rectangles, not pills. Shadows: `--shadow-1/2` are near-invisible on light;
**none** on dark (hairline borders carry all structure). `--shadow-dialog` only
for modals.

### Motion

150–250ms ease-out, opacity + ≤10px translate. Primitives: `.fade-in` (mount),
`.reveal` + `<Reveal>` (scroll, fires once), `.skeleton` (1.5s opacity pulse),
`.live-dot` (2.4s pulse — the only infinite animation). Everything is disabled
by the `prefers-reduced-motion` block. Nothing spins, floats, or glows.

---

## Components

### CSS primitives (globals.css)

`.btn` + `--primary` (ink-filled) / `--accent` (emerald) / `--secondary`
(hairline) / `--ghost`, sizes `--sm/--lg` · `.input` (accent focus ring) ·
`.card` / `.panel` · `.badge--pos/neg/warn/neutral/accent` · `.seg` +
`.seg__btn[aria-pressed]` segmented control · `.metric-row` (dt/dd data rows) ·
`.data-table` · `.skeleton` · `.container` (1120px, 12-col-friendly gutters) ·
`.faq-item` (styled details/summary) · grid helpers: `.hero-grid`, `.split-2`,
`.terminal-grid-main/three/four` — all collapse for mobile.

### React components

```
components/
├── ui/            Logo (mark + wordmark) · Dialog (focus trap, Esc, scroll
│                  lock, focus restore) · Skeleton · EmptyState · Reveal
├── marketing/     SiteHeader (sticky, mobile menu) · SiteFooter · MacroStrip
│                  (live FRED readout) · TerminalPreview (static, real data)
│                  · NewsPreview (live, 4 stories) · AuthShell
├── news/          NewsExplorer (URL-synced search/filter/pagination,
│                  SWR-style refetch) · NewsCard (lead + row variants)
└── terminal/      TerminalHeader · CommandBar · CompanyBand (+VerdictChip)
                   · PriceChart (recharts, volume overlay, lazy-loaded)
                   · KeyStats · Fundamentals (52-week range bar) · MacroPanel
                   · SentimentPanel · Headlines · UpgradeDialog (Razorpay)
```

### Data layer

```
lib/
├── types.ts        Raw API shapes (captured from the live backend) + normalized
│                   UI types + news types
├── api.ts          Fetchers + normalizers — components never see raw shapes
├── format.ts       fmtPrice / fmtNum / fmtPct / timeAgo — single source of truth
├── usage.ts        Free-tier daily counter (v1-compatible localStorage keys)
├── clerk-appearance.ts
└── news/
    ├── sources.ts  Feed registry (every feed optional at runtime)
    ├── parse.ts    RSS 2.0 + Atom parser (pure, unit-tested)
    ├── classify.ts Keyword categorizer (pure, unit-tested)
    └── index.ts    Aggregation: 6s/feed timeout, allSettled, title dedupe,
                    5-min in-memory cache + CDN s-maxage, health reporting
```

---

## Rules that keep it coherent

1. Numbers always render in `.num` (tabular mono) so columns of figures align.
2. Uppercase labels are 11px and rare — they mark sections, not sentences.
3. The serif appears only on editorial surfaces (public site); the terminal is
   sans + mono only.
4. Green/red/amber always mean position/direction/caution — never branding.
5. New surfaces must work in both themes with zero component changes: style
   with tokens, never hex.
6. Interactive targets ≥32px (usually 40px); focus-visible ring on everything.
