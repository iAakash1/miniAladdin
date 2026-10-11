#!/usr/bin/env python3
"""Merge the screening shards into screening_log.csv and report inter-screener agreement.

Reads shards/screen_main_NNN.json and shards/screen_dual_NNN.json plus data/candidates_pool.jsonl, writes:

  screening_log.csv      one row per screened record (identifiers, our decision fields, no abstract text)
  screening_summary.json counts by decision / exclusion code / family / publication status, coverage of the pool,
                         dual-screen agreement (raw agreement and Cohen's kappa on include/maybe/exclude)

Records the main screen did not cover (a failed batch) are listed as `not_screened` rather than silently dropped.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SHARDS = BASE / "shards"
POOL = BASE / "data" / "candidates_pool.jsonl"


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    if not n:
        return float("nan")
    labels = sorted({x for p in pairs for x in p})
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def load(prefix: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(SHARDS.glob(f"{prefix}_*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception as err:  # noqa: BLE001
            print(f"unreadable {path.name}: {err}")
            continue
        for d in data.get("decisions", []):
            out[d["pool_id"]] = d
    return out


def main() -> None:
    pool = {p["pool_id"]: p for p in map(json.loads, POOL.open())}
    main_d, dual_d = load("screen_main"), load("screen_dual")
    rows = []
    for pid, p in pool.items():
        d = main_d.get(pid)
        row = {
            "pool_id": pid, "title": p["title"], "year": p["year"], "authors": "; ".join(p["authors"][:4]), "venue": p["venue"],
            "doi": p["doi"], "arxiv": p["arxiv"], "cited_by_at_retrieval": p["cited_by"], "sources": "|".join(p["sources"]),
            "queries": "|".join(p["queries"]), "seed": p.get("seed", False), "has_abstract": len(p["abstract"] or "") > 200,
        }
        if d:
            row.update({k: (";".join(v) if isinstance(v, list) else v) for k, v in d.items() if k != "pool_id"})
        else:
            row["decision"] = "not_screened"
        rows.append(row)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (BASE / "screening_log.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    pairs = [(main_d[i]["decision"], dual_d[i]["decision"]) for i in dual_d if i in main_d]
    bin_pairs = [("in" if a != "exclude" else "out", "in" if b != "exclude" else "out") for a, b in pairs]
    screened = [r for r in rows if r["decision"] != "not_screened"]
    summary = {
        "pool": len(pool), "screened_main": len(main_d), "not_screened": len(pool) - len(main_d),
        "decisions": dict(Counter(r["decision"] for r in screened)),
        "exclusion_codes": dict(Counter(r.get("exclusion_code", "") for r in screened if r["decision"] == "exclude")),
        "pub_status": dict(Counter(r.get("pub_status", "") for r in screened if r["decision"] != "exclude")),
        "evidence_type": dict(Counter(r.get("evidence_type", "") for r in screened if r["decision"] != "exclude")),
        "families_include_or_maybe": dict(Counter(f for r in screened if r["decision"] != "exclude" for f in str(r.get("families", "")).split(";") if f)),
        "dual_screen": {"n": len(pairs), "raw_agreement_3class": (sum(a == b for a, b in pairs) / len(pairs)) if pairs else None,
                        "kappa_3class": kappa(pairs), "raw_agreement_in_vs_out": (sum(a == b for a, b in bin_pairs) / len(bin_pairs)) if pairs else None,
                        "kappa_in_vs_out": kappa(bin_pairs)},
    }
    (BASE / "screening_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
