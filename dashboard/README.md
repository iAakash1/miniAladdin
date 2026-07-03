# OmniSignal — web app

Next.js 16 app: public editorial site (`/`, `/news`) + authenticated dark
terminal (`/terminal`). Design and architecture documented in
[`../docs/REDESIGN.md`](../docs/REDESIGN.md),
[`../docs/DESIGN-SYSTEM.md`](../docs/DESIGN-SYSTEM.md) and
[`../docs/QA.md`](../docs/QA.md).

## Develop

```bash
npm install
npm run dev     # http://localhost:3000
npm test        # news pipeline unit tests
npm run lint
npm run build
```

## Environment

| Variable | Where | Purpose |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Vercel + local | Clerk auth |
| `CLERK_SECRET_KEY` | Vercel + local | Clerk auth (middleware) |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | Vercel + local | Razorpay Checkout in the browser (intentionally public) |
| `RAZORPAY_KEY_ID` | Vercel + local | Server-only key ID for order creation (API routes never read `NEXT_PUBLIC_*`) |
| `RAZORPAY_KEY_SECRET` | Vercel | Order creation + webhook HMAC — never exposed to the browser |
| `API_URL` | optional | FastAPI base (defaults to the Railway deployment) |
| `NEXT_PUBLIC_SITE_URL` | optional | Canonical URL for metadata/sitemap |

## Structure

```
src/
├── app/
│   ├── (site)/          public: landing, /news (light editorial)
│   ├── terminal/        authenticated app (dark, force-dynamic, own ClerkProvider)
│   ├── sign-in|sign-up/ Clerk pages in the editorial shell
│   ├── api/news/        live RSS aggregation (cached, resilient)
│   ├── payment/         Razorpay order + verify (unchanged flow)
│   ├── sitemap.ts · robots.ts · not-found.tsx · layout.tsx · globals.css
├── components/          ui/ · marketing/ · news/ · terminal/
├── lib/                 types · api (normalizers) · format · usage · news/
└── middleware.ts        public vs. protected routes
```

Routing notes: `/api/news` is an app route and takes precedence over the
catch-all `/api/*` rewrite to the FastAPI backend; the marketing pages ship
no Clerk or chart JavaScript.
