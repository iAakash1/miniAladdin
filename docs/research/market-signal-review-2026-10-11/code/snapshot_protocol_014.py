#!/usr/bin/env python3
"""Preserve a copy of the EXP-014 protocol as it stands before the registered run: `validation/exp014_protocol_pre_run.json`.

The file holds the canonical definition, the fingerprint, the SHA-256 of every method file and input registry, the SHA-256 of the preregistration document and of the rehearsal manifest, and the git state at the
time of writing. It is committed together with the preregistration, so the protocol that was frozen can be compared byte for byte with whatever the run later reports.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/snapshot_protocol_014.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.quant.study import exp014, prereg  # noqa: E402

OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/exp014_protocol_pre_run.json"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def main() -> None:
    doc = REPO / exp014.PREREG_DOC
    if not doc.exists():
        sys.exit("write docs/EXP_014_PREREGISTRATION.md first (code/make_prereg_doc_014.py)")
    fp = exp014.definition_fingerprint(REPO)
    if f"Definition fingerprint: `{fp}`" not in doc.read_text(encoding="utf-8"):
        sys.exit("the preregistration document does not embed the current fingerprint: regenerate it")
    rehearsal = REPO / "experiments/EXP-014_rehearsal/manifest.json"
    snapshot = {
        "purpose": "protocol frozen before the registered EXP-014 run; compare with experiments/EXP-014/definition.json and the manifest after the run",
        "definition_fingerprint": fp,
        "definition": exp014.DEFINITION,
        "method_sources_sha256": {m: prereg.sha256_file(REPO / m) for m in exp014.METHOD_SOURCES},
        "inputs_registry": {"path": str(exp014.INPUTS_FILE), "sha256": prereg.sha256_file(REPO / exp014.INPUTS_FILE)},
        "preregistration": {"path": str(exp014.PREREG_DOC), "sha256": prereg.sha256_file(doc)},
        "rehearsal_manifest_sha256": prereg.sha256_file(rehearsal) if rehearsal.exists() else None,
        "git_parent_of_registration_commit": git("rev-parse", "HEAD"),
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "note": "the registration commit itself cannot contain its own identifier; the run's manifest records it as registration_commit",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT} (fingerprint {fp[:16]}..., {len(snapshot['method_sources_sha256'])} method files)")


if __name__ == "__main__":
    main()
