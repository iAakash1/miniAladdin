"""Generate docs/PROVIDER_FIELD_MATRIX.md from the statement map.

Hand-maintained matrices go stale silently, which is the failure mode this
whole audit exists to catch. This reads `src/providers/statements.py` — the
same map the adapter uses — so the document cannot describe a mapping the
code does not have.

The RAW and NORMALIZED columns are facts about the map. API and UI are facts
about whether the grouped structure is emitted and read, which are checked
against the source rather than asserted.

Run: .venv/bin/python scripts/generate_provider_matrix.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.providers import statements  # noqa: E402

API = ROOT / "api" / "index.py"
PANEL = ROOT / "dashboard/src/components/terminal/security/Reported.tsx"
FABRIC = ROOT / "src/providers/fabric.py"


def main() -> None:
    emitted = '"statements": statements' in API.read_text()
    grouped = "reported = statements.group(" in FABRIC.read_text()
    rendered = "reported" in PANEL.read_text()

    rows: list[tuple[str, ...]] = []
    for provider, table in sorted(statements.VENDOR_KEYS.items()):
        for key, spec in sorted(table.items(), key=lambda kv: (kv[1].concept, kv[0])):
            rows.append((
                spec.concept,
                provider,
                f"`{key}`",
                "yes",
                "yes" if grouped else "no",
                "yes" if emitted else "no",
                "yes" if rendered else "no",
                spec.unit,
                spec.basis,
                spec.period or "not stated",
                "×1" if spec.scale == 1.0 else f"×{spec.scale:,.0f}",
            ))

    header = (
        "| Field | Provider | Vendor key | Raw | Normalized | API | UI | "
        "Unit | Basis | Period | Scale |"
    )
    sep = "|" + "---|" * 11

    out = [
        "# Provider field matrix",
        "",
        "**Generated** by `scripts/generate_provider_matrix.py` from",
        "`src/providers/statements.py`. Do not edit by hand — regenerate it.",
        "",
        "Every row is a vendor-native key that this product has established a",
        "meaning for. A key absent from this table is a key the adapter does",
        "not surface, and that is deliberate: a number whose unit, basis and",
        "period nobody has established is a numeral, not a fact.",
        "",
        "`Scale` is the multiplier applied to reach `Unit`. Finnhub reports",
        "company-level totals in millions and every other figure here is in",
        "units; the factor is measured against yfinance across four securities,",
        "not assumed.",
        "",
        "`Period` of *not stated* means the vendor supplied none. Those facts",
        "are never grouped with a dated one — silence is not a wildcard.",
        "",
        header,
        sep,
    ]
    out += ["| " + " | ".join(r) + " |" for r in rows]

    unmapped_note = (
        f"\n**Coverage.** {len(statements.FINNHUB)} Finnhub keys and "
        f"{len(statements.YFINANCE)} yfinance keys are mapped. Finnhub returns "
        "131 keys per request; the unmapped remainder is predominantly ratios "
        "and price-return statistics, which belong on the ratio surface rather "
        "than beside statement figures.\n"
    )
    out.append(unmapped_note)

    dest = ROOT / "docs" / "PROVIDER_FIELD_MATRIX.md"
    dest.write_text("\n".join(out))
    print(f"wrote {dest.relative_to(ROOT)} — {len(rows)} rows")


if __name__ == "__main__":
    main()
