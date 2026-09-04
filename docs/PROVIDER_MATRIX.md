# Provider capability matrix

Generated from the adapters themselves, not written by hand. Every row below
was derived by reflecting over the `VendorClient` subclasses the application
actually constructs and reading which `get_*` methods they implement. If a
capability is missing here, no adapter implements it — this is not a list of
things we intend to support.

Regenerate with the snippet at the end of this file.

## The four states this matrix distinguishes

They are different, and collapsing them is how a product tells a reader
"unavailable" when it means "we never asked".

| state | meaning |
|---|---|
| **provider unsupported** | No adapter implements the capability. Nothing to configure. |
| **credential missing** | An adapter exists; this environment has no key, so it reports itself unavailable and every chain skips it. |
| **local unavailable** | A credential exists on the deployment (Render) but not here. Architecturally exercisable, not locally verifiable. |
| **request failed** | Credential present, request made, provider refused or errored. The only one that is a fault. |

## Capabilities

| capability | providers implementing it | local credential | status |
|---|---|---|---|
| price | finnhub, fmp, marketstack, massive (key absent), polygon, tiingo (key absent), twelvedata, yfinance | 6 of 8 keyed | usable locally |
| series | fmp, marketstack, massive (key absent), polygon, tiingo (key absent), twelvedata, yfinance | 5 of 7 keyed | usable locally |
| company | finnhub, fmp, massive (key absent), polygon, tiingo (key absent), yfinance | 4 of 6 keyed | usable locally |
| fundamentals | alpha_vantage (key absent), finnhub, fmp, tiingo (key absent), yfinance | 3 of 5 keyed | usable locally |
| ownership | yfinance | 1 of 1 keyed | usable locally |
| filings | sec | 1 of 1 keyed | usable locally |
| xbrl_facts | sec | 1 of 1 keyed | usable locally |
| news | gnews, newsapi (key absent), tavily, tiingo (key absent), yahoo_rss | 3 of 5 keyed | usable locally |
| macro | fred | 1 of 1 keyed | usable locally |
| analyst_targets | alpha_vantage (key absent), finnhub | 1 of 2 keyed | usable locally |
| analyst_consensus | yfinance | 1 of 1 keyed | usable locally |
| options | — | — | **no adapter implements this** |
| quote | tiingo (key absent) | 0 of 1 keyed | **credential missing — not locally testable** |

## What this tells us

**Options are not supported by any adapter.** Not "unconfigured" — unwritten.
This is the single most important line in the table and it decides Phase C.

**SEC is keyless and carries the deepest data we have.** Filings, XBRL facts
and XBRL timelines require no credential and are the source of the six fiscal
years of financial statements now on the security page. It is the most
under-used provider in the stack.

**Ownership, macro and analyst consensus each have exactly one provider.**
There is no fallback for any of them. If yfinance stops answering, ownership
disappears — correctly reported as unavailable, but with nothing behind it.

**Estimates do not exist.** No adapter returns forward estimates. Anything in
the interface that would need them is not "missing data", it is a capability
this stack does not have.

**Massive is keyed on the deployment, not here.** It leads the price, series
and company chains when present. Locally it is skipped, which is why the
1,744 backend tests pass unchanged with it installed.

## Massive: what was verified without a credential

Established against the live service by probing unauthenticated, which
involves no secret:

| endpoint | probe result | meaning |
|---|---|---|
| `/v2/aggs/ticker/{t}/range/…` | 401 `API Key was not provided` | exists; Polygon-compatible |
| `/v3/reference/tickers/{t}` | 401 | exists |
| `/v3/snapshot/options/{underlying}` | 401 | **options chain exists** |
| `/v3/reference/options/contracts` | 401 | **contract discovery exists** |

A wrong key returns `Unknown API Key` rather than `API Key was not provided`,
which is how both auth mechanisms were confirmed. The key travels in an
`Authorization` header, never a query string.

**What could not be verified:** whether the deployment's plan entitles it to
options data. A 401 proves the route exists; it says nothing about
entitlement. Massive's published tiers gate real-time data and streaming
separately, so an options request under this key may return data, an
entitlement error, or delayed data — and there is no way to know which from
here.

## Streaming

Massive publishes WebSocket access on higher tiers. No adapter implements it,
no capability in the table needs it today, and entitlement is unverifiable
from this environment. See the streaming decision recorded in Phase G.

## Regenerating this table

```
.venv/bin/python - <<'PY'
import inspect, os
from src.providers.base import VendorClient
import src.providers.vendors.market_vendors as mv, src.providers.vendors.massive_vendor as mav
import src.providers.vendors.tiingo_vendor as tv, src.providers.vendors.data_vendors as dv
import src.providers.vendors.news_vendors as nv, src.providers.vendors.sec_vendor as sv
seen = {}
for m in [mv, mav, tv, dv, nv, sv]:
    for _, obj in vars(m).items():
        if inspect.isclass(obj) and issubclass(obj, VendorClient) and obj is not VendorClient:
            seen[obj.NAME] = obj
for nm, cls in sorted(seen.items()):
    caps = sorted(n[4:] for n in vars(cls) if n.startswith("get_"))
    keyed = cls.KEY_ENV is None or bool(os.getenv(cls.KEY_ENV, ""))
    print(f"{nm:<14} {'keyed' if keyed else 'NO KEY':<8} {', '.join(caps)}")
PY
```

---

# Streaming: the decision, and why

**Decision: not implemented. Consciously rejected for now, not deferred by
neglect.**

The brief asks what actually benefits from streaming before asking whether to
build it. Working through the candidates against this product as it stands:

| surface | would streaming help? | why |
|---|---|---|
| quotes on the security page | marginally | One symbol, already refreshed on a 30-second hub timer. A reader looking at one company is not trading it here. |
| watchlist | marginally | Same hub, same timer, and the list is short. |
| order status | **yes, in principle** | An order moving from `accepted` to `filled` is the one event a reader is actually waiting on. |
| positions / portfolio | no | They move when orders fill; the fill is the event. |
| market breadth | no | Recomputed from a 20-second snapshot. Sub-second breadth is not a thing. |
| historical charts | no, ever | REST is authoritative for history. Streaming must never become a second, inconsistent truth. |

So exactly one surface has a real case: **order status**. And that is an
Alpaca stream, not a Massive one — the broker knows when an order fills, the
market-data vendor does not.

Three facts make building it now the wrong call:

1. **No credential.** Alpaca paper is unconfigured in this environment and
   Massive's WebSocket entitlement is unverifiable. A streaming layer that
   cannot be connected to anything is a layer whose reconnect, backoff,
   stale-detection and cleanup paths have never executed. That is worse than
   no layer: it is untested infrastructure that looks tested because it
   compiles.

2. **The one surface that benefits does not exist in a form that needs it.**
   Orders are placed one at a time from a ticket that already shows the
   broker's reply. Nobody is watching a blotter.

3. **The existing hub already has the hard parts.** `quote-hub.ts` does
   reference-counted subscription, one request per symbol set, a single
   timer, last-observed state on failure, and cleanup on the last
   unsubscribe. Those are the guarantees the brief lists. A stream would
   replace its transport, not its design — which means the work is smaller
   later and the design is already validated.

**What would change this:** an Alpaca paper credential plus a surface where
several orders are live at once. At that point the right move is to extend
the existing hub's transport rather than introduce a parallel subscription
system, because two subscription models is precisely how a terminal ends up
with two prices for one symbol.

**What was explicitly not done:** no placeholder stream client, no dormant
WebSocket abstraction, no configuration flag for a feature that does not
exist. An interface that pretends to be live is the failure mode this whole
product is built against.
