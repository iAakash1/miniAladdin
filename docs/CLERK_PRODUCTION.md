# Clerk: development instance today, and what a production instance needs

**OWNER ACTION REQUIRED.** Moving to a production instance needs a domain, DNS and a Clerk account that only the
owner has. The summary and the other owner actions are in `OWNER_ACTIONS.md`; this page is the detail.

## What is deployed (verified 2026-10-08)

| | |
|---|---|
| Instance | **Development** - the publishable key begins `pk_test_`, and its Frontend API host is `caring-snipe-24.clerk.accounts.dev` |
| Vercel Production and Preview | The **same** five Clerk variables, created 127 days ago (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `NEXT_PUBLIC_CLERK_SIGN_IN_URL`, `…SIGN_UP_URL`, `…AFTER_SIGN_IN_URL`, `…AFTER_SIGN_UP_URL`) |
| Backend | `CLERK_JWKS_URL` and `CLERK_ISSUER` point at the same development instance |
| Symptom | Responses carry `x-clerk-auth-reason: dev-browser-missing`; Clerk shows its development-mode banner and applies development rate limits |

## Why it is a development instance

This is not a mistake in the repository and not something it can fix. A Clerk
**production** instance requires:

1. a **custom domain the owner controls** - Clerk does not issue production
   instances for `*.vercel.app`, and the site is served from
   `omnisignalterminal.vercel.app`;
2. **DNS records** for that domain (a CNAME for the Frontend API host, and for
   the account portal and email), added at the registrar;
3. the **owner's Clerk dashboard**, to create the production instance, configure
   social providers' production credentials (Google, etc. need their own OAuth
   clients), and copy the `pk_live_` / `sk_live_` keys.

None of those is available to the build or to this repository. Fabricating a
configuration would only produce a site that cannot sign anyone in.

## What the owner does to move

1. Buy or choose a domain; add it to the Vercel project.
2. In Clerk: create the production instance for that domain; add the DNS records
   it lists; wait for verification.
3. In Vercel (Production only): set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` to the
   `pk_live_…` key and `CLERK_SECRET_KEY` to the `sk_live_…` key. Leave Preview on
   the development keys.
4. Redeploy the frontend. The Content-Security-Policy follows the new key
   automatically (the host is read from it).
5. For the backend (Cloud Run), set `CLERK_JWKS_URL` and `CLERK_ISSUER` to the
   production instance's, and deploy a new revision (secrets and env are read at
   start-up).
6. Set `CLERK_AUTHORIZED_PARTIES` on the backend to the production origin(s), after
   confirming a real session token's `azp` claim: it is opt-in so that a wrong
   value cannot lock everyone out. With it set, a token minted for any other
   origin on the instance is refused.

## Origins, redirects and the other places the domain appears

Do these together with the steps above, in the production instance's dashboard and in the two deployments.
Clerk's menu names change between dashboard versions: look under its Domains and Paths settings.

| Where | What |
|---|---|
| Clerk, production instance | Make the custom domain the instance's primary domain. Set the sign-in, sign-up and after-sign-in paths to the values already in the Vercel variables (`NEXT_PUBLIC_CLERK_SIGN_IN_URL`, `…SIGN_UP_URL`, `…AFTER_SIGN_IN_URL`, `…AFTER_SIGN_UP_URL`). Allow the production origin for redirects. For each social sign-in (Google and so on) create that provider's own OAuth client and register the redirect URI Clerk shows you; the development instance's shared credentials do not carry over |
| Vercel, Production only | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (`pk_live_…`), `CLERK_SECRET_KEY` (`sk_live_…`), and `NEXT_PUBLIC_SITE_URL` set to the new origin, so the sitemap, robots file and page metadata name it. Leave Preview on the development keys |
| Cloud Run | `CLERK_JWKS_URL` and `CLERK_ISSUER` for the production instance, and `ALLOWED_ORIGINS` extended with the new origin. Use "Changing backend configuration safely" in `OWNER_ACTIONS.md` |
| Cloud Run, last | `CLERK_AUTHORIZED_PARTIES`, after you have read a real session token's `azp` claim (below) |

Nothing in the repository names the development instance: the Content-Security-Policy reads the Clerk
host from the publishable key (a `pk_live_` key on a custom domain is allowed automatically, and a
malformed key allows nothing), and the backend reads only the two variables above.

## After the switch: verify the authorization boundaries

1. **Anonymous.** `curl -s -o /dev/null -w '%{http_code}\n' https://<your domain>/api/watchlists` must print
   `401`; the same for `/api/research/AAPL`. `/api/macro`, `/api/build` and `/api/news` stay `200`.
2. **Direct to Cloud Run, no identity.** `curl -s -o /dev/null -w '%{http_code}\n' <service URL>/api/health` must print `403`.
3. **Signed in as the owner.** The terminal loads; a company page runs its research; paper-trading status loads.
4. **Signed in as someone else** (a second account). Their watchlists and notes are their own; another
   user's object id answers `404`; paper trading, admin and metrics-reset answer `403`.
5. **`azp`.** In the browser's developer tools, read the `__session` cookie and decode its payload locally
   (do not paste a token into a website). Its `azp` is your production origin. Set
   `CLERK_AUTHORIZED_PARTIES` to that origin, release a new revision, and confirm step 3 still works.
   A wrong value locks everyone out, so keep the previous revision name ready for rollback.

## What the repository guarantees regardless

Verified in source and pinned by tests (`tests/test_authorization_matrix.py`,
`tests/test_clerk_auth.py`, `dashboard/tests/edge-auth.test.ts`):

| Caller | Backend | Edge (Vercel) |
|---|---|---|
| Anonymous, protected API route | **401** | **401** JSON `{"detail":"Sign in required."}` (was a 404 rewrite) |
| Anonymous, protected page | - | Clerk redirects a document request to sign-in |
| Unverifiable token | **401** | - |
| Authentication not configured | **503** - fails closed, never open | - |
| Signed-in user, another user's object | **404** - deliberately indistinguishable from "does not exist", so ids cannot be enumerated; the object is left untouched | - |
| Signed-in user lacking a permission (paper trading, admin, metrics reset) | **403** | - |
| Owner | allowed | allowed |
| Cloud Run directly, no Google identity | **403** (IAM) | - |
