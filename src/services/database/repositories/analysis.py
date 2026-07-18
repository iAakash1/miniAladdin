"""Analysis history: automatic persistence of every completed research run,
plus the deterministic comparison between any two stored runs.

The complete research response is stored in quant_payload (JSONB) so a past
analysis can be re-rendered by the existing frontend components and compared
factor-by-factor without recomputation. All arithmetic in compare() is plain
Python over stored engine output — the LLM is never asked to compute deltas.
"""

from __future__ import annotations

import re
from typing import Any, Optional

_SEARCH_SAFE = re.compile(r"[^\w .&\-^]")

SUMMARY_COLUMNS = (
    "id,ticker,company_name,verdict,confidence,risk_level,composite_score,created_at"
)

# Family order mirrors the research report's attribution section.
FAMILY_LABELS = {
    "momentum": "Momentum",
    "quality": "Quality",
    "fundamental": "Value",
    "news": "News",
    "reversal": "Reversal",
}
_EPSILON = 0.005  # below this absolute delta a contribution counts as unchanged


class AnalysisRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    # ── writes ───────────────────────────────────────────────────────────────
    def record(self, clerk_user_id: str, research: dict[str, Any]) -> Optional[str]:
        """Persist one completed /api/research response. Returns the row id."""
        quant = research.get("quant") or {}
        row = {
            "clerk_user_id": clerk_user_id,
            "ticker": research.get("ticker"),
            "company_name": (research.get("technicals") or {}).get("company_name"),
            "verdict": research.get("verdict") or "Hold",
            "confidence": research.get("confidence"),
            "risk_level": research.get("risk_level"),
            "composite_score": quant.get("raw_score"),
            # The COMPLETE deterministic payload — nothing thrown away.
            "quant_payload": research,
            "ai_report": research.get("ai"),
        }
        data = self._c.table("analysis_history").insert(row).execute().data
        return data[0]["id"] if data else None

    def delete(self, clerk_user_id: str, history_id: str) -> bool:
        rows = (
            self._c.table("analysis_history")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", history_id)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return False
        self._c.table("analysis_history").delete().eq("id", history_id).eq(
            "clerk_user_id", clerk_user_id
        ).execute()
        return True

    # ── reads ────────────────────────────────────────────────────────────────
    def get(self, clerk_user_id: str, history_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self._c.table("analysis_history")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", history_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def list(
        self,
        clerk_user_id: str,
        *,
        ticker: Optional[str] = None,
        verdict: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None,
        sort: str = "newest",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        query = (
            self._c.table("analysis_history")
            .select(SUMMARY_COLUMNS, count="exact")
            .eq("clerk_user_id", clerk_user_id)
        )
        if ticker:
            query = query.eq("ticker", ticker.strip().upper())
        if verdict:
            query = query.eq("verdict", verdict)
        if date_from:
            query = query.gte("created_at", date_from)
        if date_to:
            query = query.lte("created_at", date_to)
        if search:
            # PostgREST or_() treats , ( ) % as syntax — keep a conservative
            # character set rather than trying to escape.
            term = _SEARCH_SAFE.sub("", search.strip())[:60]
            if term:
                query = query.or_(f"ticker.ilike.%{term}%,company_name.ilike.%{term}%")

        if sort == "oldest":
            query = query.order("created_at", desc=False)
        elif sort == "confidence":
            query = query.order("confidence", desc=True).order("created_at", desc=True)
        else:  # newest
            query = query.order("created_at", desc=True)

        offset = (page - 1) * page_size
        result = query.range(offset, offset + page_size - 1).execute()
        return {
            "items": result.data,
            "total": result.count or 0,
            "page": page,
            "page_size": page_size,
        }

    # ── saved reports (bookmarks over history rows) ──────────────────────────
    def list_saved(self, clerk_user_id: str) -> list[dict[str, Any]]:
        saved = (
            self._c.table("saved_reports")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .order("saved_at", desc=True)
            .execute()
            .data
        )
        if not saved:
            return []
        history_ids = [row["analysis_history_id"] for row in saved]
        summaries = {
            row["id"]: row
            for row in (
                self._c.table("analysis_history")
                .select(SUMMARY_COLUMNS)
                .eq("clerk_user_id", clerk_user_id)
                .in_("id", history_ids)
                .execute()
                .data
            )
        }
        return [
            {**row, "analysis": summaries.get(row["analysis_history_id"])}
            for row in saved
        ]

    def save_report(
        self,
        clerk_user_id: str,
        history_id: str,
        custom_title: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        if self.get(clerk_user_id, history_id) is None:
            return None
        payload: dict[str, Any] = {
            "clerk_user_id": clerk_user_id,
            "analysis_history_id": history_id,
        }
        if custom_title is not None:
            payload["custom_title"] = custom_title.strip()[:120] or None
        if notes is not None:
            payload["notes"] = notes
        rows = (
            self._c.table("saved_reports")
            .upsert(payload, on_conflict="clerk_user_id,analysis_history_id")
            .execute()
            .data
        )
        return rows[0] if rows else None

    def _saved_owned(self, clerk_user_id: str, saved_id: str) -> bool:
        rows = (
            self._c.table("saved_reports")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", saved_id)
            .limit(1)
            .execute()
            .data
        )
        return bool(rows)

    def update_saved(
        self,
        clerk_user_id: str,
        saved_id: str,
        *,
        custom_title: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        if not self._saved_owned(clerk_user_id, saved_id):
            return None
        patch: dict[str, Any] = {}
        if custom_title is not None:
            patch["custom_title"] = custom_title.strip()[:120] or None
        if notes is not None:
            patch["notes"] = notes
        if not patch:
            return None
        rows = (
            self._c.table("saved_reports")
            .update(patch)
            .eq("id", saved_id)
            .eq("clerk_user_id", clerk_user_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_saved(self, clerk_user_id: str, saved_id: str) -> bool:
        if not self._saved_owned(clerk_user_id, saved_id):
            return False
        self._c.table("saved_reports").delete().eq("id", saved_id).eq(
            "clerk_user_id", clerk_user_id
        ).execute()
        return True

    # ── deterministic comparison ─────────────────────────────────────────────
    def compare(
        self, clerk_user_id: str, id_a: str, id_b: str
    ) -> Optional[dict[str, Any]]:
        """Factor-level deltas between two stored runs (older → newer)."""
        row_a = self.get(clerk_user_id, id_a)
        row_b = self.get(clerk_user_id, id_b)
        if row_a is None or row_b is None:
            return None
        # Normalize direction: a = older ("before"), b = newer ("after").
        if (row_a.get("created_at") or "") > (row_b.get("created_at") or ""):
            row_a, row_b = row_b, row_a
        return {
            "before": _run_summary(row_a),
            "after": _run_summary(row_b),
            "same_ticker": row_a.get("ticker") == row_b.get("ticker"),
            "factors": _factor_deltas(row_a, row_b),
            "families": _family_deltas(row_a, row_b),
            "macro": _macro_delta(row_a, row_b),
            "risk": _risk_delta(row_a, row_b),
        }


# ── comparison helpers (module-level, unit-testable) ─────────────────────────

def _payload(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("quant_payload") or {}


def _quant(row: dict[str, Any]) -> dict[str, Any]:
    return _payload(row).get("quant") or {}


def _run_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "ticker": row.get("ticker"),
        "company_name": row.get("company_name"),
        "verdict": row.get("verdict"),
        "confidence": row.get("confidence"),
        "risk_level": row.get("risk_level"),
        "composite_score": row.get("composite_score"),
        "created_at": row.get("created_at"),
    }


def _factor_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    factors = _quant(row).get("factors") or []
    return {
        f["name"]: f
        for f in factors
        if isinstance(f, dict) and f.get("name") and f.get("score") is not None
    }


def _factor_deltas(row_a: dict[str, Any], row_b: dict[str, Any]) -> list[dict[str, Any]]:
    before, after = _factor_map(row_a), _factor_map(row_b)
    out: list[dict[str, Any]] = []
    for name in sorted(set(before) | set(after)):
        b = (before.get(name) or {}).get("contribution")
        a = (after.get(name) or {}).get("contribution")
        delta = round((a or 0.0) - (b or 0.0), 4)
        out.append(
            {
                "name": name,
                "family": (after.get(name) or before.get(name) or {}).get("family"),
                "before": b,
                "after": a,
                "delta": delta,
                "changed": abs(delta) >= _EPSILON or (b is None) != (a is None),
            }
        )
    out.sort(key=lambda item: abs(item["delta"]), reverse=True)
    return out


def _family_deltas(row_a: dict[str, Any], row_b: dict[str, Any]) -> list[dict[str, Any]]:
    def sums(row: dict[str, Any]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for f in _factor_map(row).values():
            family = f.get("family")
            if family:
                totals[family] = totals.get(family, 0.0) + (f.get("contribution") or 0.0)
        return totals

    before, after = sums(row_a), sums(row_b)
    out = []
    for family in FAMILY_LABELS:
        if family not in before and family not in after:
            continue
        b, a = before.get(family), after.get(family)
        delta = round((a or 0.0) - (b or 0.0), 4)
        out.append(
            {
                "family": family,
                "label": FAMILY_LABELS[family],
                "before": None if b is None else round(b, 4),
                "after": None if a is None else round(a, 4),
                "delta": delta,
                "changed": abs(delta) >= _EPSILON,
            }
        )
    return out


def _macro_delta(row_a: dict[str, Any], row_b: dict[str, Any]) -> dict[str, Any]:
    def srm(row: dict[str, Any]) -> Optional[float]:
        return (_payload(row).get("macro") or {}).get("risk_multiplier")

    def gate(row: dict[str, Any]) -> Optional[float]:
        return _quant(row).get("macro_gate")

    b_srm, a_srm = srm(row_a), srm(row_b)
    b_gate, a_gate = gate(row_a), gate(row_b)
    return {
        "srm_before": b_srm,
        "srm_after": a_srm,
        "srm_delta": None if b_srm is None or a_srm is None else round(a_srm - b_srm, 4),
        "gate_before": b_gate,
        "gate_after": a_gate,
    }


def _risk_delta(row_a: dict[str, Any], row_b: dict[str, Any]) -> dict[str, Any]:
    b, a = _quant(row_a).get("risk_score"), _quant(row_b).get("risk_score")
    return {
        "score_before": b,
        "score_after": a,
        "score_delta": None if b is None or a is None else a - b,
        "level_before": row_a.get("risk_level"),
        "level_after": row_b.get("risk_level"),
    }
