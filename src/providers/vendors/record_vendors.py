"""Official records about a company that no market-data vendor carries.

Each source answers one kind of question and is asked only that question:

  * the Federal Register — documents federal agencies published that name
    the company (investigations, rules, orders, notices)
  * openFDA — FDA enforcement reports (recalls) where the company is the
    recalling firm
  * ClinicalTrials.gov — active studies the company sponsors

None of this is evidence for the signal. These are primary records a reader
can open and judge; the deterministic engine never reads them.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from src.providers.base import VendorClient

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _fda_day(raw: Any) -> Optional[str]:
    text = str(raw or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if re.fullmatch(r"\d{8}", text) else None


class FederalRegisterVendor(VendorClient):
    """FederalRegister.gov full-text search for documents naming a company."""

    NAME = "federal_register"
    KEY_ENV = None
    DEFAULT_RPM = 20
    URL = "https://www.federalregister.gov/api/v1/documents.json"
    FIELDS = ("document_number", "title", "type", "publication_date", "agencies", "html_url")
    #: Exchange rule filings list widely held stocks as examples (a new
    #: options series "on NVDA"). They name the company and say nothing
    #: about it, so they are counted and left out.
    ROUTINE_PREFIX = "self-regulatory organizations"

    def get_official_actions(self, names: list[str], limit: int = 8) -> Optional[dict[str, Any]]:
        phrases = [name for name in dict.fromkeys(n.strip() for n in names) if name]
        if not phrases:
            return None
        data = self._get_json(
            self.URL,
            params={
                "conditions[term]": " | ".join(f'"{name}"' for name in phrases),
                "order": "newest",
                "per_page": 20,
                "fields[]": list(self.FIELDS),
            },
            operation="official_actions",
        )
        if not isinstance(data, dict):
            return None
        documents, routine = [], 0
        for row in data.get("results") or []:
            if not isinstance(row, dict):
                continue
            title = _clip(row.get("title"), 220)
            day = str(row.get("publication_date") or "")
            url = str(row.get("html_url") or "")
            if not title or not _DAY.match(day) or not url.startswith("https://www.federalregister.gov/"):
                continue
            if title.lower().startswith(self.ROUTINE_PREFIX):
                routine += 1
                continue
            documents.append({
                "id": str(row.get("document_number") or ""),
                "title": title,
                "type": str(row.get("type") or "Document"),
                "published": day,
                "agencies": [
                    str(a.get("name")) for a in row.get("agencies") or []
                    if isinstance(a, dict) and a.get("name")
                ][:3],
                "url": url,
            })
        return {
            "query": phrases,
            "total": int(data.get("count") or 0),
            "routine_excluded": routine,
            "documents": documents[:limit],
        }


class OpenFdaVendor(VendorClient):
    """openFDA enforcement reports: recalls where the company is the firm."""

    NAME = "openfda"
    KEY_ENV = "OPENFDA_API_KEY"
    DEFAULT_RPM = 40
    BASE = "https://api.fda.gov"
    KINDS = {"drug": "/drug/enforcement.json", "device": "/device/enforcement.json"}

    def _is_empty_answer(self, response: Any) -> bool:
        if getattr(response, "status_code", None) != 404:
            return False
        try:
            return (response.json().get("error") or {}).get("code") == "NOT_FOUND"
        except (ValueError, AttributeError):
            return False

    def get_recalls(self, firm: str, kind: str, limit: int = 5) -> Optional[dict[str, Any]]:
        path = self.KINDS.get(kind)
        firm = firm.strip().replace('"', "")
        if path is None or not firm:
            return None
        data = self._get_json(
            self.BASE + path,
            params={
                "search": f'recalling_firm:"{firm}"',
                "sort": "report_date:desc",
                "limit": min(max(limit, 1), 20),
                "api_key": self.api_key,
            },
            operation="regulatory_recalls",
        )
        if data is None:
            # openFDA's own "No matches found!" — answered, nothing on record.
            return {"kind": kind, "firm": firm, "total": 0, "recalls": []}
        if not isinstance(data, dict):
            return None
        total = ((data.get("meta") or {}).get("results") or {}).get("total")
        recalls = []
        for row in data.get("results") or []:
            if not isinstance(row, dict):
                continue
            reported = _fda_day(row.get("report_date"))
            if not reported:
                continue
            recalls.append({
                "id": str(row.get("recall_number") or ""),
                "classification": str(row.get("classification") or ""),
                "status": str(row.get("status") or ""),
                "reported": reported,
                "initiated": _fda_day(row.get("recall_initiation_date")),
                "firm": _clip(row.get("recalling_firm"), 90),
                "product": _clip(row.get("product_description"), 160),
                "reason": _clip(row.get("reason_for_recall"), 220),
            })
        return {
            "kind": kind, "firm": firm,
            "total": int(total) if isinstance(total, int) else len(recalls),
            "recalls": recalls,
        }


class ClinicalTrialsVendor(VendorClient):
    """ClinicalTrials.gov v2: active studies a company leads."""

    NAME = "clinicaltrials"
    KEY_ENV = None
    DEFAULT_RPM = 20
    URL = "https://clinicaltrials.gov/api/v2/studies"
    ACTIVE = "RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION,NOT_YET_RECRUITING"
    FIELDS = "NCTId,BriefTitle,Phase,OverallStatus,LeadSponsorName,StartDate,LastUpdatePostDate"

    def _count(self, sponsor: str, extra: dict[str, str]) -> Optional[int]:
        data = self._get_json(
            self.URL,
            params={"query.lead": sponsor, "filter.overallStatus": self.ACTIVE,
                    "countTotal": "true", "pageSize": 1, "fields": "NCTId", **extra},
            operation="clinical_trials",
        )
        total = data.get("totalCount") if isinstance(data, dict) else None
        return total if isinstance(total, int) else None

    def get_trials(self, sponsor: str, limit: int = 6) -> Optional[dict[str, Any]]:
        sponsor = sponsor.strip()
        if not sponsor:
            return None
        data = self._get_json(
            self.URL,
            params={
                "query.lead": sponsor, "filter.overallStatus": self.ACTIVE,
                "countTotal": "true", "pageSize": min(max(limit, 1), 20),
                "sort": "LastUpdatePostDate:desc", "fields": self.FIELDS,
            },
            operation="clinical_trials",
        )
        if not isinstance(data, dict):
            return None
        wanted = sponsor.lower()
        trials = []
        for study in data.get("studies") or []:
            section = (study or {}).get("protocolSection") or {}
            ident = section.get("identificationModule") or {}
            status = section.get("statusModule") or {}
            lead = ((section.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name") or ""
            nct = str(ident.get("nctId") or "")
            # Full-text matching can return a study another sponsor leads; a
            # trial is attributed only when its lead sponsor carries the name.
            if not re.fullmatch(r"NCT\d{8}", nct) or wanted not in lead.lower():
                continue
            trials.append({
                "id": nct,
                "title": _clip(ident.get("briefTitle"), 180),
                "phases": [str(p) for p in (section.get("designModule") or {}).get("phases") or []],
                "status": str(status.get("overallStatus") or ""),
                "sponsor": _clip(lead, 90),
                "started": (status.get("startDateStruct") or {}).get("date"),
                "updated": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
                "url": f"https://clinicaltrials.gov/study/{nct}",
            })
        total = data.get("totalCount")
        total = total if isinstance(total, int) else None
        return {
            "sponsor": sponsor,
            "active_total": total,
            # One more count, not a page walk: how much of the active
            # programme is in late-stage (Phase 3) testing. Skipped when the
            # sponsor leads nothing active, where the answer is already known.
            "phase3_active": (
                0 if total == 0 else self._count(sponsor, {"filter.advanced": "AREA[Phase]PHASE3"})
            ),
            "trials": trials,
        }
