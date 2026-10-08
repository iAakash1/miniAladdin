# Dependency audit

A dated record of what the dependency scanners reported, what was changed, and what was
deliberately left alone and why. Re-run it before a release; the commands are at the end.

## 2026-10-08

### Frontend (`dashboard/`)

`npm audit --omit=dev` reported three findings (one critical, two high):

| Package | Finding | Reachable here? | Action |
|---|---|---|---|
| `next` 16.3.5 | RCE in `next/og` `ImageResponse` (fixed 16.3.6); SSRF in image optimisation, SSG/ISR cache poisoning, Draft Mode leak (fixed 16.3.8) | No: no `ImageResponse` (the Open Graph images are static files), no SSG/ISR pages (every page renders per request), no `next/image` | Upgraded to **16.3.8** (patch release on the same minor line) |
| `sharp` 0.35.4 | librsvg vulnerability (fixed 0.35.5) | Only through Next's image optimiser, which is unused | Upgraded to 0.35.5 with Next |
| `source-map-js` 1.2.1 | event-loop denial of service through a crafted source map (fixed 1.2.2) | Build-time only | Upgraded to 1.2.2 |

`npm audit --omit=dev` now reports **0 vulnerabilities**. The full `npm audit` still lists five
high findings in the lint toolchain (`braces`, reached through `eslint-config-next`). They run on a
developer's machine and in CI, never in the deployed application, and the fix is a major version of
the lint config; deferred.

### Backend (`requirements.txt`)

`pip-audit` against the project's installed packages reported advisories in ten packages (two of them dev tools). What
production *actually installs* was read from the image's build log, because only exact pins are
fixed and the rest resolve at build time:

| Package | In the image | Advisories | Action |
|---|---|---|---|
| `PyJWT` | 2.13.0 (pinned) | 14, mostly algorithm confusion with HMAC keys and key-handling edge cases. This service allows only `RS256` with Clerk's JWKS, so most are unreachable. Reachable ones are denial-of-service class: a bearer token with an arbitrary `kid` or a pathological header | Pinned **2.15.0**. Token verification also now fails closed on any exception (a deeply nested header raised `RecursionError` past the `PyJWTError` handler on 2.13.0 and became a 500) |
| `aiohttp` | 3.14.1 (pinned) | 3: client/server parser denial of service | Pinned **3.14.3** |
| `urllib3` | 2.8.0 | fixed in 2.8.0 | none (resolved fresh at build) |
| `h2` | 4.4.1 | fixed in 4.4.1 | none |
| `multidict` | 6.9.1 | fixed in 6.9.1 | none |
| `soupsieve` | 2.10 | fixed in 2.9.0 | none |
| `cryptography` | 49.0.0 (pinned) | PYSEC-2026-3552: a PKCS#7 decryption oracle (fixed 50.0.0) | **Not changed.** The service never calls PKCS#7, S/MIME or any decryption; `cryptography` is present for RS256 verification. A major-version bump of the crypto library under the token verifier is a change to make deliberately, with a real token to test against |
| `pyarrow` | 18.1.0 (pinned) | PYSEC-2026-113: use-after-free reading an Arrow IPC *file* with pre-buffering (fixed 23.0.1) | **Not changed.** The service reads and writes parquet only, and only its own committed files. The package also underlies the research panel storage, which this pass does not touch |
| `pytest`, `pip` | dev tools | advisories | not shipped |

A local virtualenv can lag the image: the first scan flagged `urllib3`, `h2`, `multidict` and
`soupsieve` only because the developer's environment was older than the image built from the same
requirements.

### Secrets

No scanner binary is installed locally; the repository runs `gitleaks` on every push (workflow
"Secret scan", passing). A pattern sweep over the 7,800 lines added in this pass found nothing.

## Re-running

```bash
cd dashboard && npm audit --omit=dev
python3 -m venv /tmp/pa && /tmp/pa/bin/pip install pip-audit
/tmp/pa/bin/pip-audit --path .venv/lib/python3.12/site-packages     # the project's packages
```

To audit what a release really contains, read the `Successfully installed ...` line from its Cloud
Build log (`gcloud builds log <build-id>`) instead of trusting a local environment.
