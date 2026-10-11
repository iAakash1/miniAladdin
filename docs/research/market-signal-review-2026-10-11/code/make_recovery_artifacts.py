#!/usr/bin/env python3
"""Build the recovery artifacts from what survives on disk: no model calls, no network.

Writes under recovery/:
  task_inventory.csv            one row per screening agent (batch, status, tokens, deliverable on disk, recovery action)
  recovered_screening.csv/.json decisions that exist only because they were recovered (written to disk by agents that were
                                 later stopped by the usage limit, or produced by the validated triage classifier);
                                 identifiers and decision fields only, no abstracts
  web_evidence_index.csv        the web documentation fetched by the stopped dataset agents (URL/query, size, usable?)
and the full recovered web text under data/ (git-ignored, search/fetch snippets are not redistributed).
Relies on recovery/transcript_audit.csv (code/audit_transcripts.py).
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REC = BASE / "recovery"
TASKS = Path("/private/tmp/claude-501/-Users-aakashjawle-Downloads-omnisignal-final/d9fc792f-acf7-4ed5-9f65-6c45655243bc/tasks")
WF = Path.home() / ".claude/projects/-Users-aakashjawle-Downloads-omnisignal-final/d9fc792f-acf7-4ed5-9f65-6c45655243bc/subagents/workflows"


def text_of(content) -> str:
    return content if isinstance(content, str) else " ".join(b.get("text", "") for b in content if isinstance(b, dict))


def main() -> int:
    audit = {r["id"]: r for r in csv.DictReader((REC / "transcript_audit.csv").open()) if r["kind"] == "agent-task"}
    ledger = {r["pool_id"]: r for r in csv.DictReader((BASE / "screening_log.csv").open())}
    rows, recovered = [], []
    for tid, a in sorted(audit.items(), key=lambda kv: kv[1]["first"]):
        target = ""
        for line in (TASKS / f"{tid}.output").open():
            r = json.loads(line)
            if r.get("type") == "user":
                m = re.search(r"shards/(screen_(main|dual)_(\d+))\.json", text_of(r["message"]["content"]))
                target = m.group(1) if m else ""
                break
        if not target:
            continue
        shard = BASE / "shards" / f"{target}.json"
        valid, n = False, 0
        if shard.exists():
            try:
                n = len(json.loads(shard.read_text())["decisions"])
                valid = True
            except Exception:  # noqa: BLE001
                pass
        limit = bool(a["error"])
        status = "failed (usage limit)" if limit else "completed"
        action = ("none: deliverable on disk" if valid and not limit else
                  "recovered from file written before the stop" if valid and limit else
                  "unrecoverable: stopped before writing; reasoning not persisted -> triage classifier" if target.startswith("screen_main")
                  else "unrecoverable; not rerun (dual sample is a 10% agreement check, 141 of 241 records already double-screened)")
        rows.append({"task_id": tid, "batch": target.replace("screen_", ""), "status": status, "turns": a["turns"], "tool_calls": a["tool_calls"],
                     "tokens_in_out_cache_create": a["tok_in_out_cc"], "tokens_cache_read": a["tok_cache_read"],
                     "wrote_file_in_transcript": bool(a["writes"]), "shard_valid_on_disk": valid, "records": n, "recovery_action": action})
        if valid and limit:
            for d in json.loads(shard.read_text())["decisions"]:
                recovered.append({"pool_id": d["pool_id"], "decision": d["decision"], "families": ";".join(d.get("families", [])),
                                  "relevance": d.get("relevance"), "provenance": "recovered_from_file_after_agent_stopped",
                                  "source_batch": target.replace("screen_", "")})
    for r in csv.DictReader((REC / "classifier_assisted.csv").open()):
        recovered.append({"pool_id": r["pool_id"], "decision": r["decision"], "families": "", "relevance": "", "provenance": "classifier_assisted",
                          "source_batch": "unscreened", "p_relevant": r["p_relevant"]})
    fields = ["task_id", "batch", "status", "turns", "tool_calls", "tokens_in_out_cache_create", "tokens_cache_read",
              "wrote_file_in_transcript", "shard_valid_on_disk", "records", "recovery_action"]
    with (REC / "task_inventory.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    rf = ["pool_id", "decision", "families", "relevance", "provenance", "source_batch", "p_relevant"]
    with (REC / "recovered_screening.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rf, lineterminator="\n")
        w.writeheader()
        w.writerows(recovered)
    (REC / "recovered_screening.json").write_text(json.dumps(recovered, indent=1))

    # web evidence from the stopped dataset agents
    web = []
    for f in sorted(glob.glob(str(WF / "wf_79773971-ca3/agent-*.jsonl"))):
        label = json.load(open(f.replace(".jsonl", ".meta.json"))).get("label", "")
        calls = {}
        for line in open(f):
            r = json.loads(line)
            c = (r.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if b.get("type") == "tool_use" and b.get("name") in ("WebFetch", "WebSearch"):
                    calls[b["id"]] = (b["name"], b["input"])
                if b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                    name, inp = calls[b["tool_use_id"]]
                    body = text_of(b.get("content") or "")
                    web.append({"agent": label.replace("data:", ""), "tool": name, "target": inp.get("url") or inp.get("query"),
                                "prompt": (inp.get("prompt") or "")[:300], "chars": len(body), "usable": len(body) > 400, "text": body})
    (BASE / "data").mkdir(exist_ok=True)
    (BASE / "data/web_evidence_recovered.jsonl").write_text("\n".join(json.dumps(w) for w in web))
    with (REC / "web_evidence_index.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["agent", "tool", "target", "chars", "usable"], lineterminator="\n")
        w.writeheader()
        w.writerows({k: x[k] for k in w.fieldnames} for x in web)
    print(json.dumps({"agents": len(rows), "recovered_rows": len(recovered), "web_results": len(web), "web_usable": sum(x["usable"] for x in web)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
