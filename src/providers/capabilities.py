"""The capability registry — the architectural source of truth.

Every question this system can ask a vendor is declared here exactly once,
together with everything downstream code needs to know about it: which method
answers it, whether answering costs a network call, whether it participates in
the parallel evidence fan-out, how multiple vendors' answers are combined, and
which failure modes it can genuinely produce.

**Why a registry rather than a table of names.** Capability metadata was
previously spread across two parallel dicts (`CAPABILITY_METHODS` and
`CAPABILITY_LABELS`) which nothing forced to agree. A capability could be
registered with a method and no label, or a label and no method, and neither
mistake produced an error — the first showed as a blank row in the diagnostics
surface, the second was invisible until a fan-out silently collected nothing.
Both are now impossible to express: a `Capability` cannot be constructed
without both, and the legacy dicts are *derived* from this registry rather
than maintained beside it.

**What the registry does not do.** It does not know which vendors exist.
Vendor support is discovered by introspection at call time (`hasattr(vendor,
capability.method)`), because a hand-kept vendor list drifts the moment an
adapter gains a method. The registry declares the *question*; the vendors
answer for themselves whether they can respond to it.

**Reconciliation is declared, not implied.** `reconciliation` records how
several vendors' answers to the same question are combined, and the values are
deliberately distinct rather than a single "merge" concept:

  ``median``       numeric agreement across venues is meaningful (prices)
  ``union``        vendors have non-overlapping coverage; take each field from
                   whoever has it, and flag conflicts
  ``distribution`` the spread across vendors *is* the finding; never collapse
  ``per_vendor``   values are venue- or convention-specific and must stay
                   attributed to the vendor that reported them
  ``dedupe``       many vendors carry the same underlying item; identity is
                   established by content, and repeats are corroboration
  ``primary``      not a vendor's interpretation but the source document
  ``none``         single-sourced; no combination step exists
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

#: Failure modes the fan-out classifier can produce. A capability declares the
#: subset it can genuinely encounter, which is what makes an unexpected status
#: worth investigating rather than shrugging at.
FAILURE_MODES = (
    "rate_limited",     # vendor answered 429
    "not_entitled",     # vendor answered 401/403 — plan does not cover this
    "timeout",          # vendor did not answer inside the budget
    "unavailable",      # vendor answered, but not usefully
    "not_configured",   # no credential present; vendor was never asked
)

RECONCILIATION_STRATEGIES = (
    "median", "union", "distribution", "per_vendor", "dedupe", "primary", "none",
)


@dataclass(frozen=True)
class Capability:
    """One question the system knows how to ask a data vendor."""

    #: Registry key. Also the string that appears in `Evidence.capability`
    #: and in every provenance record, so it is part of the API contract.
    name: str
    #: The method a vendor must implement to answer. Introspection target.
    method: str
    #: Human label for the diagnostics surface.
    label: str
    #: What the capability actually answers, for an operator reading the
    #: capability matrix without the source open.
    description: str
    #: How several vendors' answers are combined. See module docstring.
    reconciliation: str
    #: Does answering cost an HTTP request? `brand_mark` is the one that does
    #: not, and that single fact is why it is excluded from the fan-out.
    network: bool = True
    #: Does this capability run through `fabric.collect`? A capability outside
    #: the fabric produces no Evidence and no provenance, so this is exactly
    #: the flag an audit needs in order to ask "why not".
    fabric: bool = True
    #: Whether the answer is a primary source document rather than a vendor's
    #: reading of one. Drives how the UI marks it.
    primary_source: bool = False
    #: Whether the vendor needs a credential. Capabilities answerable without
    #: one still work in CI and when every keyed vendor is rate-limited.
    requires_auth: bool = True
    #: Failure modes this capability can genuinely produce.
    failure_modes: tuple[str, ...] = FAILURE_MODES
    #: Why a capability sits outside the fan-out, when it does. Required for
    #: any capability with `fabric=False` so no exclusion is unexplained.
    excluded_because: Optional[str] = None

    def __post_init__(self) -> None:
        if self.reconciliation not in RECONCILIATION_STRATEGIES:
            raise ValueError(
                f"{self.name}: unknown reconciliation {self.reconciliation!r}"
            )
        unknown = set(self.failure_modes) - set(FAILURE_MODES)
        if unknown:
            raise ValueError(f"{self.name}: unknown failure modes {sorted(unknown)}")
        # An unexplained exclusion is the exact thing this registry exists to
        # prevent: a capability quietly outside the evidence path with no
        # record of the decision.
        if not self.fabric and not self.excluded_because:
            raise ValueError(
                f"{self.name}: fabric=False requires excluded_because"
            )

    def supported_by(self, vendor: object) -> bool:
        """Whether this vendor can answer, by introspection."""
        return hasattr(vendor, self.method)


_ALL: tuple[Capability, ...] = (
    Capability(
        name="quote", method="get_price", label="Real-time quote",
        description="Last price and session context from one venue's tape.",
        reconciliation="median",
    ),
    Capability(
        name="series", method="get_series", label="Daily price history",
        description=(
            "Split- and dividend-adjusted daily closes. Every vendor here is "
            "held to adjusted closes; mixing a raw series into the same "
            "consensus would manufacture a conflict at every split."
        ),
        reconciliation="median",
    ),
    Capability(
        name="news", method="get_news", label="Headlines",
        description="Articles referencing the symbol, from one vendor's index.",
        reconciliation="dedupe",
    ),
    Capability(
        name="news_sentiment", method="get_news_sentiment",
        label="Scored news sentiment",
        description=(
            "Articles with a vendor's own tone score. Separate from `news` so "
            "a vendor that returns headlines without scores is never asked "
            "for something it cannot supply."
        ),
        reconciliation="per_vendor",
    ),
    Capability(
        name="company", method="get_company", label="Company profile",
        description="Identity, sector, industry, domain, listing metadata.",
        reconciliation="union",
    ),
    Capability(
        name="fundamentals", method="get_fundamentals",
        label="Reported fundamentals",
        description="Trailing margins, returns and per-share figures.",
        reconciliation="union",
    ),
    Capability(
        name="street", method="get_street", label="Analyst & insider activity",
        description="Recommendation trend and insider transaction flow.",
        reconciliation="per_vendor",
    ),
    Capability(
        name="analyst_targets", method="get_analyst_targets",
        label="Price targets",
        description="High/low/mean target prices as one vendor sees them.",
        reconciliation="distribution",
    ),
    Capability(
        name="analyst_consensus", method="get_analyst_consensus",
        label="Analyst consensus",
        description=(
            "Rating distribution and target spread. Explicitly a distribution "
            "and never a median: the median of two vendors' consensus figures "
            "is a consensus of nothing."
        ),
        reconciliation="distribution",
    ),
    Capability(
        name="ownership", method="get_ownership",
        label="Ownership & short interest",
        description=(
            "Share count, float, institutional and insider holdings, short "
            "interest. Kept apart from fundamentals so a settlement-lagged "
            "short figure is never read as being as current as a margin."
        ),
        reconciliation="per_vendor",
        requires_auth=False,
    ),
    Capability(
        name="filings", method="get_filings", label="SEC filings",
        description="Filing index straight from EDGAR.",
        reconciliation="primary", primary_source=True, requires_auth=False,
    ),
    Capability(
        name="xbrl_facts", method="get_xbrl_facts", label="XBRL reported facts",
        description="Tagged financial facts as filed.",
        reconciliation="primary", primary_source=True, requires_auth=False,
    ),
    Capability(
        name="xbrl_timeline", method="get_xbrl_timeline",
        label="Point-in-time filings",
        description=(
            "Every filing of a concept, originals preserved beside revisions. "
            "The only capability that can answer what a filing said at the "
            "time rather than what the record says now."
        ),
        reconciliation="primary", primary_source=True, requires_auth=False,
    ),
    Capability(
        name="image_search", method="search_images", label="Editorial imagery",
        description=(
            "Industry context photography, queried from the *reconciled* "
            "company profile so the query is as specific as the evidence "
            "allows."
        ),
        reconciliation="dedupe",
    ),
    Capability(
        name="brand_mark", method="get_brand", label="Company logo",
        description="The company's own mark, addressed by ticker or domain.",
        reconciliation="none",
        network=False, fabric=False,
        excluded_because=(
            "Pure URL construction with no network call. A fan-out would add "
            "a thread handoff and an evidence record for something that "
            "cannot fail, time out or rate-limit. It stays registered so the "
            "capability matrix still shows whether the logo provider is "
            "configured."
        ),
        failure_modes=("not_configured",),
    ),
)

#: Registry, keyed by capability name.
REGISTRY: dict[str, Capability] = {c.name: c for c in _ALL}

#: Legacy views, derived rather than maintained. Downstream code that only
#: needs the method or the label keeps working, and the two can no longer
#: disagree with each other because neither is written by hand.
CAPABILITY_METHODS: dict[str, str] = {c.name: c.method for c in _ALL}
CAPABILITY_LABELS: dict[str, str] = {c.name: c.label for c in _ALL}

#: Capabilities that participate in the parallel evidence fan-out.
FABRIC_CAPABILITIES: tuple[str, ...] = tuple(c.name for c in _ALL if c.fabric)


def get(name: str) -> Optional[Capability]:
    """The capability by name, or None if it is not registered."""
    return REGISTRY.get(name)


def label(name: str) -> str:
    """Display label, falling back to the raw key for unregistered names."""
    cap = REGISTRY.get(name)
    return cap.label if cap else name


def supported(vendor: object) -> list[str]:
    """Every capability this vendor can answer, by introspection."""
    return [c.name for c in _ALL if c.supported_by(vendor)]


def describe(names: Optional[Iterable[str]] = None) -> list[dict[str, object]]:
    """The registry as plain data, for the diagnostics API and the docs.

    Emitted in registry order rather than sorted, so the shape of the list
    matches the order capabilities are declared in — which groups price,
    news, profile, analyst, primary-source and visual together without
    needing a separate category field.
    """
    wanted = set(names) if names is not None else None
    return [
        {
            "name": c.name,
            "label": c.label,
            "description": c.description,
            "method": c.method,
            "reconciliation": c.reconciliation,
            "network": c.network,
            "fabric": c.fabric,
            "primary_source": c.primary_source,
            "requires_auth": c.requires_auth,
            "failure_modes": list(c.failure_modes),
            "excluded_because": c.excluded_because,
        }
        for c in _ALL
        if wanted is None or c.name in wanted
    ]
