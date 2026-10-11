#!/usr/bin/env python3
"""Account for every background agent this review has run, from the transcripts themselves.

Reads the agent transcripts that the harness keeps (JSONL): the 28 agent task outputs and the workflow agent
transcripts (`subagents/workflows/wf_*/agent-*.jsonl`) and writes `recovery/transcript_audit.csv` with one row per
agent: turns, tool calls, token usage summed from the API usage records in the transcript (four counters kept
separate, because which of them the interface displays is a question of definition and is reported, not assumed),
first and last timestamps, how the run ended, and which files the agent wrote.

Nothing is printed from transcript bodies except counts. Read-only.
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
# The two locations are local to the machine that ran the agents, so they are read from the environment rather than written into the source:
#   RECOVERY_TRANSCRIPT_HOME  the directory holding the session transcripts (it contains subagents/workflows/wf_*/agent-*.jsonl)
#   RECOVERY_TASK_OUTPUTS     the directory holding the per-agent task output files (<task id>.output)
try:
    HOME = Path(os.environ["RECOVERY_TRANSCRIPT_HOME"])
    TASKS = Path(os.environ["RECOVERY_TASK_OUTPUTS"])
except KeyError as missing:
    raise SystemExit(f"set {missing.args[0]} (see the module docstring); this script reads local transcripts and cannot run elsewhere")
WORKFLOWS = HOME / "subagents/workflows"
OUT = BASE / "recovery"


def scan(path: Path) -> dict:
    """Streaming writes repeat one assistant message across several lines, so usage is taken once per message id
    (the maximum seen for each counter). Summing every line over-counts by the number of streamed chunks."""
    msgs: dict[str, dict[str, int]] = {}
    turns = tools = 0
    first = last = ""
    writes: set[str] = set()
    last_text = ""
    error = ""
    with path.open() as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("timestamp") or ""
            first = first or ts
            last = ts or last
            msg = r.get("message") or {}
            if r.get("type") == "assistant":
                mid = msg.get("id") or r.get("uuid")
                u = msg.get("usage") or {}
                cur = msgs.setdefault(mid, {"i": 0, "o": 0, "cc": 0, "cr": 0})
                cur["i"] = max(cur["i"], u.get("input_tokens", 0) or 0)
                cur["o"] = max(cur["o"], u.get("output_tokens", 0) or 0)
                cur["cc"] = max(cur["cc"], u.get("cache_creation_input_tokens", 0) or 0)
                cur["cr"] = max(cur["cr"], u.get("cache_read_input_tokens", 0) or 0)
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if block.get("type") == "tool_use":
                            tools += 1
                            inp = block.get("input") or {}
                            cmd = str(inp.get("command", ""))
                            target = inp.get("file_path") or ""
                            if block.get("name") == "Write" and target:
                                writes.add(os.path.basename(target))
                            elif block.get("name") == "Bash" and "shards/" in cmd and ("open(" in cmd or "json.dump" in cmd):
                                writes.add("bash-written shard")
                        elif block.get("type") == "text" and block.get("text"):
                            last_text = block["text"]
                            if "session limit" in block["text"].lower() or "hit your" in block["text"].lower():
                                error = "usage/session limit"
                err = r.get("error") or msg.get("error")
                if err and not error:
                    error = str(err)[:120]
    turns = len(msgs)
    i = sum(m["i"] for m in msgs.values()); o = sum(m["o"] for m in msgs.values())
    cc = sum(m["cc"] for m in msgs.values()); cr = sum(m["cr"] for m in msgs.values())
    return {"turns": turns, "tool_calls": tools, "tok_input": i, "tok_output": o, "tok_cache_create": cc, "tok_cache_read": cr,
            "tok_in_out_cc": i + o + cc, "first": first, "last": last, "writes": ";".join(sorted(writes)),
            "ended_with": last_text[:90].replace("\n", " "), "error": error}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    rows = []
    for f in sorted(TASKS.glob("*.output")):
        if f.stat().st_size == 0:
            continue
        r = scan(f)
        rows.append({"kind": "agent-task", "run": "", "id": f.stem, "label": "", **r})
    for wf in sorted(WORKFLOWS.glob("wf_*")):
        for f in sorted(wf.glob("agent-*.jsonl")):
            label = ""
            meta = f.with_suffix(".meta.json")
            if meta.exists():
                try:
                    label = json.loads(meta.read_text()).get("label") or json.loads(meta.read_text()).get("description") or ""
                except Exception:  # noqa: BLE001
                    pass
            r = scan(f)
            rows.append({"kind": "workflow-agent", "run": wf.name, "id": f.stem.replace("agent-", ""), "label": label, **r})
    fields = list(rows[0].keys())
    with (OUT / "transcript_audit.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "transcripts audited ->", OUT / "transcript_audit.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
