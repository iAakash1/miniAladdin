#!/usr/bin/env python3
"""Split the screening pool into fixed batches for independent title/abstract screening.

Records are ordered by a hash of their pool id (a deterministic shuffle, so no batch is all high-ranked or all
low-ranked and screening drift cannot line up with retrieval rank). A deterministic 10% sample (hash bucket) is
also written as a second, differently batched set for independent dual screening; agreement between the two
screens is reported in 01_REVIEW_PROTOCOL.md.

Writes data/screen_batches/batch_NNN.jsonl and data/screen_dual/batch_NNN.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data"
BATCH = 100


def h(text: str, salt: str) -> int:
    return int(hashlib.sha256((salt + text).encode()).hexdigest(), 16)


def slim(p: dict) -> dict:
    return {
        "pool_id": p["pool_id"], "title": p["title"], "year": p["year"], "authors": p["authors"][:4],
        "venue": p["venue"], "venue_type": p.get("venue_type", ""), "type": p["type"], "cited_by": p["cited_by"],
        "abstract": (p["abstract"] or "")[:1500], "has_abstract": len(p["abstract"] or "") > 200,
        "doi": p["doi"], "arxiv": p["arxiv"], "sources": p["sources"], "query_families": p["families"],
        "seed": p.get("seed", False),
    }


def write_batches(records: list[dict], folder: Path) -> int:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    n = 0
    for i in range(0, len(records), BATCH):
        n += 1
        with (folder / f"batch_{n:03d}.jsonl").open("w") as fh:
            for r in records[i:i + BATCH]:
                fh.write(json.dumps(slim(r)) + "\n")
    return n


def main() -> None:
    pool = [json.loads(line) for line in (OUT / "candidates_pool.jsonl").open()]
    ordered = sorted(pool, key=lambda p: h(p["pool_id"], "screen-v1"))
    n = write_batches(ordered, OUT / "screen_batches")
    dual = sorted((p for p in pool if h(p["pool_id"], "dual-v1") % 10 == 0), key=lambda p: h(p["pool_id"], "dual-order"))
    m = write_batches(dual, OUT / "screen_dual")
    print(json.dumps({"pool": len(pool), "batches": n, "dual_sample": len(dual), "dual_batches": m, "batch_size": BATCH}))


if __name__ == "__main__":
    main()
