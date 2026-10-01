"""The official record around a company: agency documents, recalls, trials.

Composed from three public sources, each asked only the question it answers
(see `src/providers/vendors/record_vendors.py`). The registrant's legal name
and SIC industry come from EDGAR, so routing never guesses from a ticker:
FDA and ClinicalTrials.gov are consulted only when the SEC classifies the
company in a healthcare industry.

Every section reports how it ended — answered with records, answered with
none, unavailable, not configured, or not applicable — because "no recalls"
and "the recall database did not answer" must never look the same.

Nothing here reaches the signal, confidence or risk.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from src.providers import official_record as sources
from src.services.cache_policy import put_ttl

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 21600.0  # 6h: these records change on a daily cadence at best
MAX_CACHE_ENTRIES = 128
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()

#: SEC SIC codes for pharmaceuticals, biologics, diagnostics, medical
#: devices, their distribution, health services and biological research.
_HEALTHCARE_SIC = {
    "2833", "2834", "2835", "2836", "3826", "3841", "3842", "3843", "3844",
    "3845", "3851", "5047", "5122", "8731",
} | {str(code) for code in range(8000, 8100)}

_SUFFIX = re.compile(
    r"(?:[\s,&]+(?:INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|LLC|LP|L\.P|N\.V|NV|S\.A|SA|AG|SE)\.?)+$",
    re.IGNORECASE,
)


def core_name(registrant: str) -> str:
    """"MERCK & CO., INC." -> "MERCK"; "JOHNSON & JOHNSON" is left whole."""
    name = re.sub(r"\s*/[A-Z]{2}/?$", "", registrant.strip())  # EDGAR's "/DE/" state tags
    core = _SUFFIX.sub("", name).strip(" ,&")
    return core or name


def legal_name_phrases(registrant: str) -> list[str]:
    """The spellings an agency document uses for the registrant."""
    core = core_name(registrant)
    if not core:
        return []
    if core.upper() == registrant.strip().upper():
        return [core]
    return [f"{core}, Inc.", f"{core} Inc.", f"{core} Corporation", f"{core} Corp.",
            f"{core} & Co.", f"{core} Company", f"{core} plc", f"{core} N.V."]


def _section(vendor, ask: Callable[[], Optional[dict[str, Any]]], empty: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    if not vendor.available:
        return {"status": "not_configured", "provider": vendor.NAME}
    try:
        data = ask()
    except Exception as exc:  # noqa: BLE001 — one source never fails the record
        logger.info("official record source %s unavailable: %s", vendor.NAME, type(exc).__name__)
        return {"status": "unavailable", "provider": vendor.NAME}
    if data is None:
        return {"status": "unavailable", "provider": vendor.NAME}
    return {"status": "empty" if empty(data) else "ok", "provider": vendor.NAME, **data}


def build(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper().strip()
    now = time.time()
    with _lock:
        hit = _cache.get(symbol)
    if hit and hit[0] > now:
        return hit[1]

    try:
        entity = sources.sec.get_entity(symbol)
    except Exception:  # noqa: BLE001
        logger.info("EDGAR entity lookup failed for %s", symbol, exc_info=True)
        entity = None
    if not entity or not entity.get("name"):
        # Without the registrant's legal name every search below would be a
        # guess from the ticker. Not cached, so a transient EDGAR failure
        # does not hide the record for six hours.
        return {"symbol": symbol, "entity": None, "status": "unavailable", "sections": {}}

    registrant = entity["name"]
    core = core_name(registrant)
    healthcare = entity.get("sic") in _HEALTHCARE_SIC
    not_applicable = {
        "status": "not_applicable",
        "reason": f"SEC classifies {registrant} as {entity.get('sic_description') or 'a non-healthcare industry'}.",
    }

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="record") as pool:
        federal = pool.submit(
            _section, sources.federal_register,
            lambda: sources.federal_register.get_official_actions(legal_name_phrases(registrant)),
            lambda d: not d.get("documents"),
        )
        drug = device = trials = None
        if healthcare:
            drug = pool.submit(
                _section, sources.openfda, lambda: sources.openfda.get_recalls(core, "drug"),
                lambda d: not d.get("recalls"),
            )
            device = pool.submit(
                _section, sources.openfda, lambda: sources.openfda.get_recalls(core, "device"),
                lambda d: not d.get("recalls"),
            )
            trials = pool.submit(
                _section, sources.clinicaltrials, lambda: sources.clinicaltrials.get_trials(core),
                lambda d: not d.get("active_total"),
            )
        sections = {
            "federal_register": federal.result(),
            "fda_drug_recalls": drug.result() if drug else not_applicable,
            "fda_device_recalls": device.result() if device else not_applicable,
            "clinical_trials": trials.result() if trials else not_applicable,
        }

    result = {
        "symbol": symbol,
        "entity": {**entity, "core_name": core, "healthcare": healthcare},
        "status": "ok",
        "sections": sections,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }
    # A record whose every source failed is not cached: the next reader
    # should get a fresh attempt, not six hours of a transient outage.
    if any(s.get("status") in {"ok", "empty"} for s in sections.values()):
        with _lock:
            put_ttl(_cache, symbol, now + CACHE_TTL_SECONDS, result,
                    max_entries=MAX_CACHE_ENTRIES, now=now)
    return result


def reset_for_tests() -> None:
    with _lock:
        _cache.clear()
