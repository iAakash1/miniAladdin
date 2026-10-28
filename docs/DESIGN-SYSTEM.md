# OmniSignal design system

One set of tokens, one component layer, enforced by tests. The tokens live in
`dashboard/src/styles/tokens.css`; the shared components and their styles in
`dashboard/src/components/system/` and `dashboard/src/styles/system.css`.
Older class families in `dashboard/src/app/globals.css` resolve to the same
tokens through aliases (`--bg`, `--text`, `--line`…).

---

## Foundations

### Colour

A near-black graphite is the default; light is an explicit choice made with the
theme toggle (`html[data-theme='light']`). One accent hue, an electric cyan
(`--accent`), marks the brand, the primary action and the live state. There is
no second decorative hue, and a glow is never data.

Colour is semantic. Every value that carries a state reads it from a token:

| Token | Means |
|---|---|
| `--e-pos` | positive · verified · healthy |
| `--e-neg` | negative · failure · high risk |
| `--e-warn` | partial · degraded · stale · uncertain |
| `--e-null` | unavailable · not reported |
| `--accent` / `--e-info` | interactive · informational · live |

Research and data states (`live`, `stale`, `waking`, `unavailable`, `blocked`,
`paper`, `recorded`, …) each have a `--s-*` token that aliases one of these, so
a state looks the same everywhere it appears. The `<Status>` chip renders them,
and `/terminal/handbook` keys every one in words.

### Type

`--font-sans` (Inter) for interface and prose, `--font-mono` (IBM Plex Mono) for
figures, tickers and timestamps, `--font-serif` (Newsreader) on the public site
only. Sizes come from the `--t-*` scale (10px floor at `--t-micro`; inputs are
16px on touch screens so iOS does not zoom). Weights are 400–700. Every figure
that can sit above another uses tabular, slashed-zero numerals (`.sys-num`).

### Space, radius, layers, motion

Spacing is the `--d-*` scale on a 4px base, with a 2px half-step for dense
tables and chips; odd pixel values fail a test. Radii are `--r-xs/sm/md/lg`.
Stacking layers are named (`--z-*`) and ordered so a menu sits above a drawer
and the palette above a toast. Transitions use `--t-fast/med/slow` with one
easing curve, and a hover that moves anything is gated on
`(hover: hover) and (pointer: fine)`.

---

## Components

| Component | Use |
|---|---|
| `Workbench` | Page frame for every terminal route: title, subtitle, context rail |
| `Panel` | A titled surface; header title never wraps, the subtitle gives way and stacks under it on phones |
| `Value` | Every number: one formatter (`lib/quantity.ts`) per kind — currency, percent, count, ratio — and an em dash, never a zero, when absent |
| `Status` | A state chip with its meaning as its title |
| `StateBlock` / `EmptyLine` | Loading, unavailable, blocked (signed out, not permitted) and empty states, each in words |
| `Table` / `DataTable` / `.sys-table` | Tables; numbers right-aligned in mono, wide tables scroll inside `.sys-scroll-x`, never the page |
| `Drawer` | Side panel for editors and tickets; focus moves in, Escape closes, focus returns |
| `Inspectable` / `.sys-inspectable` | A value that opens its provenance; the touch area is enlarged on coarse pointers |
| `.sys-btn` (`--primary`, `--xs`, `--micro`, `--icon`), `.sys-input`, `.sys-seg` | Controls; at least 32px on touch screens |

Times are shown in UTC with the zone named (`formatMoment`), or as a date for a
session close. A figure from a broker, a vendor or a recorded run says which.

## Rules the tests hold

`dashboard/tests/` fails the build for: an undefined token, an off-scale font
size, weight, radius, letter-spacing or transition; odd-pixel spacing; a CSS
class nothing reaches; an ungated moving hover; a dialog without focus
handling; a generic element given a name without a role; a number or date
formatted in the viewer's locale; and a new hand-built table that has not been
checked in the rendered DOM.
