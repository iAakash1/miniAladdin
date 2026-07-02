# QA checklist & verification log

Verified July 2, 2026, against a production build (`next build` + `next start`).

## Build & code health

- [x] `next build` clean — 0 errors, 0 warnings
- [x] `eslint` clean — 0 errors (strict rules incl. no-explicit-any, set-state-in-effect)
- [x] Unit tests pass — 6/6 (`npm test`): RSS 2.0 + Atom parsing, media:content
      image extraction, CDATA/entity cleanup, malformed-feed safety, classifier
      precedence and fallback
- [x] No `any` at data boundaries; raw API shapes fully typed from live captures
- [x] Dead code removed: 5 v1 components, v1 types, v1 page, root middleware,
      Tailwind (was installed, unused), lucide-react (unused), duplicate font loading

## Routes (verified by request)

- [x] `/` static, 200, ~68ms TTFB locally; title correct (no brand duplication)
- [x] `/news` static shell, 200; explorer hydrates client-side
- [x] `/api/news` 200 JSON; clamps `pageSize` 999→50 and out-of-range pages;
      invalid category → treated as `all`; total feed failure degrades to
      `items: []` + per-source health flags (no 500, response not cached)
- [x] `/terminal` unauthenticated browser request → 307 into Clerk sign-in;
      non-document request → 404 (correct machine-traffic behavior)
- [x] `/sitemap.xml`, `/robots.txt` 200 with correct contents (terminal,
      api, payment, auth pages disallowed)
- [x] Payment routes preserved at the same paths (`/payment/create-order`,
      `/payment/verify`) — HMAC verification flow untouched

## Accessibility

- [x] Skip link to `#main` on every page
- [x] Landmarks: header / nav / main / footer / labeled sections everywhere
- [x] One `h1` per page; heading levels sequential
- [x] `:focus-visible` ring (accent, 2px offset) on all interactive elements
- [x] Dialog: focus trap, Escape, backdrop click, scroll lock, focus restore,
      `aria-modal`, labelled by its title
- [x] Segmented controls use `aria-pressed`; search inputs have labels
- [x] Result and news regions are `aria-live="polite"`; charts expose
      `role="img"` with sentence-form descriptions (trend + endpoints)
- [x] `prefers-reduced-motion` kills all animation, including the live dot
- [x] Contrast: body ≥ 7:1 both themes; smallest UI text ≥ 4.5:1; semantic
      colors checked at their used sizes
- [x] Touch targets ≥ 32px; mobile menu closes on selection

## Performance

- [x] Fonts self-hosted, no external CSS request, `display: swap`
- [x] Marketing pages ship zero Clerk and zero recharts JS (route groups +
      per-page providers); recharts lazy-loads inside the terminal only
- [x] Landing page fully static; live data (macro, news preview) fetched
      client-side against cached endpoints with skeletons
- [x] News API: 5-min in-memory cache + `s-maxage=300, stale-while-revalidate=600`
      for Vercel's CDN; 6s per-feed timeout; `Promise.allSettled`
- [x] News thumbnails lazy-load (`loading="lazy"`, `decoding="async"`,
      failed images collapse cleanly)
- [x] Security headers: nosniff, DENY framing, strict referrer, permissions-policy

## Live news requirements (brief)

- [x] Real feeds (Yahoo Finance, Dow Jones/MarketWatch, CNBC), zero fake content
- [x] Auto-updating (TTL cache), cards open original articles in new tabs
- [x] Publication, category, relative time, author when present, thumbnail
      when present
- [x] Search (300ms debounce), category filter, pagination — all URL-synced
      and shareable
- [x] Loading skeletons mirror the final layout; empty and error states with
      recovery actions; per-feed graceful failure

## Known limitations / manual checks for the owner

- [ ] Razorpay checkout end-to-end (needs real keys + test card) — flow code
      unchanged from v1 apart from lazy script loading
- [ ] Clerk production keys on Vercel (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`,
      `CLERK_SECRET_KEY`) — unchanged requirement
- [ ] Lighthouse run on the deployed URL (local sandbox has no Chrome);
      architecture targets: static marketing, ~0 blocking resources, lazy
      charts/images — expected 95+ / 100 / 100 / 95+
- [ ] CNBC feeds were unreachable from the build sandbox (treated as optional
      by design); confirm they populate once deployed

## Remaining improvement opportunities

1. Persist free-tier usage server-side (Clerk metadata) — localStorage is
   trivially resettable.
2. Bookmarks on news (localStorage now that UI patterns exist) and a
   per-ticker news filter inside the terminal.
3. `opengraph-image` generation via `next/og` for richer link unfurls.
4. Command palette (⌘K) for ticker jump + recent analyses.
5. Compare view: two tickers side-by-side reusing the same panels.
6. Streamed analysis (`fetch` + server-sent progress) so the 10s full run
   shows per-source progress instead of one skeleton.
7. E2E smoke via Playwright once a staging environment exists.
