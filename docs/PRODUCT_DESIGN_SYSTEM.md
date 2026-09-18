# Product design system

> The single source of truth for how OmniSignal looks, reads, and behaves.
> Written from the code as it exists, not as it should ideally be — where the
> two disagree, this says so rather than pretending they agree.

## Visual identity

Institutional, restrained, analytical. High information density is fine;
decoration is not. Specifically:

- No neon fintech palette, no purple-gradient SaaS look, no rounded card for
  every scrap of text.
- No chatbot-first homepage. Ask OmniSignal is one panel among several, not
  the entry point.
- No fake agent avatars, no synthetic "thinking" animation for a pipeline
  that already reports real per-node timings.
- Verdicts, states and warnings never rely on colour alone — every one
  carries a word. A reader who cannot distinguish the colours must reach the
  same conclusion as one who can.

## Two token systems exist. This is the honest state, not the target.

The product actually runs on **two loosely related design token
vocabularies**, and a design-system document that pretended otherwise would
mislead the next person who opens the CSS.

**`dashboard/src/app/globals.css`** — the marketing site, `/start`, and the
Beginner (`bg__*`) and Intermediate surfaces:

```
--ink, --ink-2, --ink-3        text, in decreasing emphasis
--surface, --surface-2, --surface-3
--accent, --accent-strong, --accent-wash
--warn, --warn-wash
```

**`dashboard/src/styles/system.css`** — the Advanced terminal (`sys-*`,
`wb-*`, `xp__*`):

```
--ink, --ink-muted, --ink-faint     text, in decreasing emphasis
--rule, --rule-strong, --rule-focus  hairlines
--t-micro (10px)  units, superscripts, column qualifiers
--t-meta  (11px)  metadata, provenance, timestamps, source tags
--t-body  (13px)  table cells, panel prose
--t-title (24px)  workspace title — one per screen
--d-0..--d-7      spacing scale: 0 / 4 / 8 / 12 / 16 / 24 / 32 / 48px
--row-compact/normal/relaxed   table row heights: 22 / 28 / 34px
```

`system.css` additionally overrides its own `--d-*`, `--row-*` and `--t-body`
under a compact density (`--d-2:6px`, rows 18/22/26px) and a relaxed one
(`--d-2:10px`, rows 28/34/42px) — the density toggle a reader sets, not a
breakpoint.

**Neither system is being merged into the other in this pass.** That is a
real, sizeable refactor with a wide blast radius across every existing
component, and doing it as a side effect of a design-documentation task would
be exactly the kind of scope creep this project has repeatedly had to correct
for. What this document commits to instead: **new shared components use the
`system.css` vocabulary**, because it is the more complete one (it has a
density system, a spacing scale, and canonical states; `globals.css` has
none of the three) — see `ResearchHistory.tsx` and `EvidenceHealth.tsx` for
recent examples that already follow this.

## Typography roles

| Role | Token | Used for |
|---|---|---|
| Product/workspace title | `--t-title` (24px) | One per screen, in `Workbench`'s header |
| Panel heading | `Panel`'s `title` prop | Bold, `--ink`, sits in the panel's own rule |
| Section heading | `Section`, `sys-label` | Uppercase, `--ink-faint`, a category marker |
| Body | `--t-body` (13px) | Panel prose, table cells |
| Fine explanation | `Prose size="fine"` | Caveats, secondary explanation under a result |
| Status metadata | `--t-meta` (11px) | Timestamps, provenance, source tags |
| Numbers / financial values | `Value`, `signed()` | Tabular figures — monospace, sign-aware |
| Units | `--t-micro` (10px) | Column qualifiers ("bps", "0–100") |
| Warnings | `Prose caution` | `--warn` text colour, never colour alone |

## Spacing

Use `--d-1` through `--d-7` (4/8/12/16/24/32/48px) for everything — margins,
gaps, padding. `--gap` is the general-purpose default spacing inside a
`Panel`'s body. Do not introduce a new literal pixel value where one of these
already expresses the same distance; a value outside the scale is a signal
that the layout is improvising rather than following it.

## Surface types

Not every piece of information is a bordered rectangle. Pick the surface that
matches the information's shape:

| Surface | Component | When |
|---|---|---|
| Panel | `Panel` | The default container — a titled region with optional state, badge, source/asOf/retrievedAt footer |
| Metric strip | `Strip` | 2–6 related numbers, side by side, inside a panel |
| Table | `DataTable` / `Table` | Rows of comparable records — always this, never a hand-built `<table>` (see `table-contract.test.ts`) |
| Narrative card | `Prose` inside a `Panel` | A written explanation, not a data grid |
| Evidence block | `ClaimInspector`'s record cards | One measured value with its full provenance |
| Status block | `StateBlock` | "Nothing to show, and here is why" — loading, empty, error, blocked |
| Empty line | `EmptyLine` | A single-sentence absence, lighter than a full `StateBlock` |
| Alert / warning | `Prose caution`, `StateBlock state="blocked"` | Something the reader must not miss |
| Drawer | `sys-drawer` (`Inspector`, `ClaimInspector`) | Detail on demand, over the workspace, not replacing it |
| Timeline | `ResearchHistory`'s `.rh__timeline` | An ordered sequence of past states |
| Comparison | `Compare`, `RankAttribution`, `SinceLastAnalysis` | Two things, or two moments of one thing, side by side |
| Chart | `TimeSeries` and friends | Continuous series, never a table pretending to be one |

## Canonical states

Ten values, one meaning each, defined once in `components/system/index.tsx`
and used everywhere via `<Status state="..." />`:

| State | Meaning |
|---|---|
| `live` | Observed now, inside its freshness window |
| `recorded` | A fact read from a stored artifact — it cannot go stale |
| `stale` | Real, but past its freshness window |
| `waking` | A cold service is starting; no value yet |
| `unavailable` | Refused or absent — no value shown in its place |
| `blocked` | A research constraint prevents this, not an error |
| `experimental` | Exists and is measured, but is not promotable |
| `candidate` | Cleared the development gates; holdout not yet spent |
| `production` | Armed and serving |
| `unknown` | State could not be determined |

The wider availability vocabulary the backend serves (`EMPTY`,
`NOT_CONFIGURED`, `INSUFFICIENT_DATA`, `UNSUPPORTED`,
`DEPENDENCY_UNAVAILABLE`, `PERMISSION_DENIED`, `ERROR` — always HTTP 200,
never a bare 404/500) maps onto these ten through
`AvailabilityNote`/`isAvailable` in `components/system/Availability.tsx`. A
new empty/failure state should be expressed as one of the existing ten plus a
sentence, not a new colour.

`SIMULATION` and `PAPER` are not states in this vocabulary — they are
**badges** (`Panel`'s `badge`/`badgeTone` props), because they describe a
*mode the whole panel is in*, not a freshness or trust judgement about one
value. `WhatIfLab` and the paper order ticket both use this.

## Colour semantics

No financial state is colour-only. Every one of these renders with its word,
every time, regardless of theme:

```
BUY · HOLD · SELL
LOW · MEDIUM · HIGH  (risk)
VERIFIED · PARTIAL · CONFLICTED · STALE · UNSUPPORTED
```

`data-tone` on `.xp__signal` drives the colour; the text node is what a
colour-blind reader, a grayscale printout, or a screen reader gets. See
`signalTone()` in `lib/explore.ts` for the mapping.

## Interaction states

`loading` / `waking` / `empty` / `partial` / `stale` / `error` / `disabled` /
`permission denied` / `not configured` / `experimental` are not eleven
separate patterns — they are the ten canonical states above, rendered through
`StateBlock` or `AvailabilityNote`, plus ordinary HTML `disabled`. A new
component should reach for one of these rather than inventing a new empty-
state shape; see Phase 22 in the product backlog for the specific copy each
page should show.

## Responsive rules

**What actually exists today** is organic, not a clean four-tier system —
real breakpoints in `system.css` alone include 1800, 1440, 1280, 1180, 1024,
900, 860, 820, 760, 700 and 640px, added one at a time as specific layouts
needed them. That is worth stating plainly rather than implying a tidier
history than the CSS has.

**The target going forward**, for new work, is the four sizes below. Existing
breakpoints are not being swept into this in one pass — that is exactly the
kind of wide, low-value mechanical change this project's own retrospectives
warn against — but any new responsive rule should be written at one of these:

| Size | Width | Rule |
|---|---|---|
| Large desktop | ≥1440px | Full density. Advanced tables show every column. |
| Laptop | 1280px | Advanced rail may fold groups (`useRailGroups`); tables unchanged. |
| Tablet | 768px | Advanced rail collapses to glyphs only (`--rail-w: 46px`, confirmed at the existing 1024px breakpoint). Simple/Guided reflow to one column. |
| Mobile | 390px | Simple must work fully here: no horizontal scroll on the body, wide content scrolls in its own `.sys-scroll-x` container (asserted by `accessibility.test.ts`), touch targets at least 44px. |

Advanced/Research may keep dense tables and scroll horizontally *inside their
own container* at any width — never the page body. This is already a tested
invariant (`table-contract.test.ts`, `accessibility.test.ts`); new tables
inherit it automatically by going through `DataTable` rather than a
hand-built `<table>`.

## What this document is not

It is not a rewrite of the CSS, not a new component library, and not a
unification of the two token systems. It is the map of what exists, so the
next person extending this product — including a future pass of this same
project — extends the real thing instead of guessing at it or, worse,
starting a third vocabulary next to the two that already disagree.
