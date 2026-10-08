# OmniSignal — web app

Next.js 16 app: public editorial site (`/`, `/news`) + authenticated dark
terminal (`/terminal`). Design and architecture documented in
[`../docs/REDESIGN.md`](../docs/REDESIGN.md),
[`../docs/DESIGN-SYSTEM.md`](../docs/DESIGN-SYSTEM.md) and
[`../docs/QA.md`](../docs/QA.md).

## Develop

```bash
npm install
npm run dev        # http://localhost:3000
npm test           # frontend guard and unit tests (node:test via tsx)
npx tsc --noEmit   # typecheck
npm run lint
npm run build
```

Sign-in needs a Clerk instance that accepts `localhost`; without Clerk keys the
public pages (`/`, `/news`, `/learn`) still render, and the `/terminal/*` screens
do not. Visual review of signed-in screens is therefore a deployment-time check.

## Environment

Names only; set values in Vercel (or `.env.local`), never in the repository.

| Variable | Needed | Purpose |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | yes | Clerk authentication. The publishable key is public by design; the Content-Security-Policy derives the Clerk host from it. See [`../docs/CLERK_PRODUCTION.md`](../docs/CLERK_PRODUCTION.md) |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL`, `…SIGN_UP_URL`, `…AFTER_SIGN_IN_URL`, `…AFTER_SIGN_UP_URL` | yes | Clerk redirect targets |
| `BACKEND_ORIGIN` | yes | Base URL of the FastAPI backend that the server-side `/api/*` proxy forwards to. There is no default: a missing value is a deployment error, not a fallback to some other host. Locally, `http://127.0.0.1:8000` |
| `BACKEND_AUTH_MODE` | production | `google_oidc` for the private Cloud Run service (the proxy signs each request with a Google identity token obtained from the Vercel OIDC token through Workload Identity Federation); `none` for a local or open backend |
| `CLOUD_RUN_AUDIENCE`, `GCP_PROJECT_NUMBER`, `GCP_SERVICE_ACCOUNT_EMAIL`, `GCP_WORKLOAD_IDENTITY_POOL_ID`, `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID` | with `google_oidc` | The federation coordinates. See [`../docs/CLOUD_RUN_DEPLOYMENT.md`](../docs/CLOUD_RUN_DEPLOYMENT.md) |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | payments | Razorpay Checkout in the browser (public key id) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | payments | Server-side order creation and signature verification; never exposed to the browser |
| `NEXT_PUBLIC_LOGO_DEV_KEY` | optional | Publishable logo key |
| `NEXT_PUBLIC_SITE_URL` | optional | Canonical URL for metadata and the sitemap |
| `CSP_MODE` | optional | `enforce` (default), `report-only` or `off`. See [`../docs/CONTENT_SECURITY_POLICY.md`](../docs/CONTENT_SECURITY_POLICY.md) |

## Structure

```
src/
├── app/
│   ├── (site)/          public: landing, /news, /learn
│   ├── terminal/        the signed-in workbench (/terminal/*)
│   ├── sign-in|sign-up/ Clerk pages
│   ├── api/news/        RSS aggregation (cached, tolerant of one failing source)
│   ├── api/[...path]/   server-side proxy to the backend (signs each request)
│   ├── api/build/       the commit and deployment this build came from
│   ├── api/csp-report/  receives Content-Security-Policy violation reports
│   ├── payment/         Razorpay order + verify
│   └── layout.tsx       renders every page per request (the CSP nonce needs it)
├── components/          system/ (design system) · terminal/ · company/ · news/ · ...
├── lib/                 api (normalisers) · csp · format · quantity · news/ · ...
├── styles/              tokens.css · system.css
└── proxy.ts             per-request Content-Security-Policy, and sign-in for pages and /api/*
```

Every response carries a Content-Security-Policy with a fresh nonce. An anonymous
request to `/api/*` is answered `401` at the edge rather than forwarded, except
for the public routes `/api/news`, `/api/macro`, `/api/build` and `/api/csp-report`. A page
that needs the Clerk SDK must go through `components/auth/NonceClerkProvider`
(tests fail if `ClerkProvider` is used directly).

Routing notes: `/api/news`, `/api/build` and `/api/csp-report` are app routes and take
precedence over the `api/[...path]` catch-all, which proxies every other `/api/*`
request to the FastAPI backend; the marketing pages ship
no Clerk or chart JavaScript, though they are now rendered per request like every other page.
