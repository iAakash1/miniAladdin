# OmniSignal design system — Graphite

One set of tokens, one component layer, enforced by tests. The tokens live in
`dashboard/src/styles/tokens.css`; the shared components and their styles in
`dashboard/src/components/system/` and `dashboard/src/styles/system.css`.
`dashboard/src/styles/overdrive.css` is the finish layer, loaded last from
`app/layout.tsx`: it holds the cross-cutting decisions below (sentence case,
flat surfaces, neutral controls) so they apply to every screen at once rather
than being repeated per page. Older class families in
`dashboard/src/app/globals.css` resolve to the same tokens through aliases
(`--bg`, `--text`, `--line`…).

---

## Principles

1. **Colour is data.** The interface itself is neutral graphite. The only hues
   on a screen are the ones that mean something: a gain, a loss, a warning, a
   sector. A button, a link or a selected tab is never green, blue or gold.
2. **Emphasis comes from ink, not hue.** The primary action is solid ink on the
   surface (near-white on dark, near-black on light). Selection is an ink
   underline or a raised surface, not a coloured fill.
3. **Flat, ruled surfaces.** Panels are a surface and a 1px rule. No gradients,
   glows, glass or background grids.
4. **Sentence case.** Labels, panel titles, table heads, badges and states are
   written as a reader says them ("Not configured", "Last checked"). Uppercase is
   kept only for short literal tags that are codes: `STALE`/`LIVE` freshness
   chips, `DEFAULT`, `RECORDED`, the paper ribbon.
5. **Figures line up.** Every figure that can sit above another uses tabular,
   slashed-zero numerals. Prose never does: Inter's tabular feature widens the
   hyphen, so "post-earnings" set tabular reads as "post - earnings".
6. **A row keeps one line.** A table row shows its figures and one or two direct
   actions; the rest are one press away in an `ActionMenu`.

## Foundations

### Colour

Dark is the default; light is an explicit choice made with the theme toggle
(`html[data-theme='light']`). Both are neutral greys with no tint.

| Role | Dark | Light |
|---|---|---|
| Page (`--p-base`) | `#0b0b0b` | `#f6f6f5` |
| Panel (`--p-panel`) | `#141414` | `#ffffff` |
| Raised / hover (`--p-raised`, `--p-hover`) | `#1a1a1a` / `#1f1f1f` | `#fafafa` / `#f3f3f2` |
| Rule / strong rule (`--rule`, `--rule-strong`) | `#242424` / `#333333` | `#e6e6e4` / `#d2d2cf` |
| Ink / muted / faint | `#ededed` / `#a9a9a9` / `#8f8f8f` | `#141414` / `#4a4a48` / `#61615e` |
| Primary action (`--grad-signal`) | near-white | near-black |

`--accent` is a neutral (`#e6e6e6` dark, `#666666` light). The browser
`theme-color` (`lib/theme.ts`) equals `--p-base`, and the sign-in widget's
accent literal (`lib/clerk-appearance.ts`) equals the light `--accent`; both
are held by tests.

Semantic colour is the only colour, and every value that carries a state reads
it from a token:

| Token | Dark | Light | Means |
|---|---|---|---|
| `--e-pos` | `#4fb286` | `#1d7a4e` | positive · verified · healthy |
| `--e-neg` | `#e5675f` | `#b5372f` | negative · failure · high risk |
| `--e-warn` | `#d39b4a` | `#8a5810` | partial · degraded · stale · uncertain |
| `--e-null` | `#8c8c8c` | `#666663` | unavailable · not reported |
| `--e-info` | ink-muted | ink-muted | informational |

Research and data states (`live`, `stale`, `waking`, `unavailable`, `blocked`,
`paper`, `recorded`, …) each have a `--s-*` token that aliases one of these, so
a state looks the same everywhere it appears. The `<Status>` chip renders them;
`/terminal/handbook` keys every one in words. Sector hues are muted, desaturated
tones so a sector map reads as categories rather than signals.

### Type

| Token | Face | Use |
|---|---|---|
| `--font-sans` | Inter | interface and prose |
| `--font-mono` | Inter, tabular | figures, prices, counts (`.num`, `.sys-num`) |
| `--font-code` | IBM Plex Mono | keyboard keys, ids, hashes, dataset and version strings |
| `--font-serif` | Newsreader | the public site's display italic only |

`--font-mono` keeps its name because many rules reference it, but it now means
"figure", not "monospace": Inter with `tabular-nums slashed-zero` aligns
columns without a typewriter face. Sizes come from the `--t-*` scale (10px
floor; inputs are 16px on touch screens so iOS does not zoom). Weights are
400–700. Panel titles are 600 at `--t-body`; metric-strip figures are 600 at
`--t-title`.

### Space, radius, layers, motion

Spacing is the `--d-*` scale on a 4px base, with a 2px half-step for dense
tables and chips; odd pixel values fail a test. Radii are `--r-xs/sm/md/lg`.
Stacking layers are named (`--z-*`) and ordered so a menu sits above a drawer
and the palette above a toast. Transitions use `--t-fast/med/slow` with one
easing curve, and a hover that moves anything is gated on
`(hover: hover) and (pointer: fine)`. Breakpoints come from a fixed list held by
a test (480, 560, 640, 720, 760, 860, 900, 980, 1023, 1100, 1180, 1280).

---

## Components

| Component | Use |
|---|---|
| `Workbench` | Page frame for every terminal route: title, subtitle, context rail |
| `Panel` | A titled surface; the header title never wraps, the subtitle gives way and stacks under it on phones. A badge is sentence case |
| `Strip` | A row of figures inside a panel, separated from the prose around it |
| `Value` | Every number: one formatter (`lib/quantity.ts`) per kind — currency, percent, count, ratio — and an em dash, never a zero, when absent |
| `Status` | A state chip with its meaning as its title; the label is shown in sentence case whatever the source casing |
| `StateBlock` / `EmptyLine` | Loading, unavailable, blocked (signed out, not permitted) and empty states, each in words; `EmptyLine` stacks a title over its explanation |
| `ActionMenu` | A row's secondary actions behind one button: a real menu (arrows, Home/End, Escape returns focus), positioned against the viewport so a scrolling table cannot clip it. Items are actions, links, group labels and separators; a destructive item is `tone: 'danger'` and opens an inline confirm rather than acting |
| `Table` / `DataTable` / `.sys-table` | Tables; figures right-aligned and tabular, wide tables scroll inside `.sys-scroll-x`, never the page. At 640px and below the tracker and alert tables become one card per row |
| `Drawer` | Side panel for editors and tickets; focus moves in, Escape closes, focus returns |
| `Inspectable` / `.sys-inspectable` | A value that opens its provenance; the touch area is enlarged on coarse pointers |
| `.sys-btn` (`--primary`, `--danger`, `--xs`, `--micro`, `--icon`), `.sys-input`, `.sys-seg` | Controls; at least 32px on touch screens. Primary is solid ink; danger is the negative tone and is used only to confirm |

Times are shown in UTC with the zone named (`formatMoment`), or as a date for a
session close. A figure from a broker, a vendor or a recorded run says which.

### Screen patterns

- **Tracker (watchlists).** Lists on the left; the selected list framed as one
  panel. Each row: symbol (with tags, note and an alert count), price, change,
  period return, trend, quote freshness with its source and time, research, then
  "Set alert" and an `ActionMenu` (paper order, note and tags, move, move to
  list, remove).
- **Alerts.** Counts above the work; alerts and the notification inbox in the
  main column, the new-alert editor beside them (stacked below 980px). Deleting
  an alert takes a second, explicit step.
- **System health.** Summary strip, process figures, then one component list
  sorted most serious first: name and tier, state, reason and version.

## Rules the tests hold

`dashboard/tests/` fails the build for: an undefined token, an off-scale font
size, weight, radius, letter-spacing or transition; odd-pixel spacing; a
breakpoint off the list; a CSS class nothing reaches; an ungated moving hover; a
dialog without focus handling; a generic element given a name without a role; a
number or date formatted in the viewer's locale; a `theme-color` or sign-in
accent that drifts from its token; a badge class missing from `system.css`; and
a new hand-built table that has not been checked in the rendered DOM.
