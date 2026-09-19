"""
The preregistration gate — shared by every study that registers before running.

A preregistration is only worth something if it demonstrably came first. So the
runner does not ask whether a document exists; it checks that the document

  (a) is tracked by git,
  (b) embeds the fingerprint of the definition it is about to execute — the
      canonical definition plus the source of every file that defines the method,
  (c) has no uncommitted change (in it or in any method file), and
  (d) sits in a commit that is already an ancestor of `origin/main`.

(b) makes the definition, the code and the document one object: change any of them
and the fingerprint moves, the document no longer matches, and the run is refused
until a visible, dated amendment is committed. (d) is what makes "before
executing" checkable rather than promised.

EXP-009A carries its own copy of this logic (written first, before this was
generalised); this module is what EXP-009B and later studies use.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence


class PreregistrationError(RuntimeError):
    """Raised when a run is attempted without a valid, pushed preregistration."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def fingerprint(definition: dict[str, Any], method_sources: Sequence[str], root: Path = Path(".")) -> str:
    """sha256 over the canonical definition and the bytes of every method file."""
    payload = {
        "definition": definition,
        "method_sources": {p: sha256_file(Path(root) / p) for p in method_sources},
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True, default=str).encode())


def _git(*args: str, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def check(
    *,
    document: Path,
    expected_fingerprint: str,
    method_sources: Sequence[str],
    root: Path = Path("."),
    fetch: bool = True,
) -> dict[str, Any]:
    """Refuse unless the preregistration is committed, unchanged and already pushed."""
    root = Path(root)
    doc = root / document
    if not doc.exists():
        raise PreregistrationError(f"{document} does not exist; write and push it before running")
    if f"Definition fingerprint: `{expected_fingerprint}`" not in doc.read_text(encoding="utf-8"):
        raise PreregistrationError(
            "the preregistration does not embed this definition's fingerprint "
            f"({expected_fingerprint[:16]}...): the definition or a method source changed after "
            "registration, or the document was not updated. Nothing is run."
        )
    if _git("ls-files", "--error-unmatch", str(document), root=root).returncode != 0:
        raise PreregistrationError("the preregistration is not tracked by git")
    tracked = [str(document), *method_sources]
    dirty = _git("status", "--porcelain", "--", *tracked, root=root).stdout.strip()
    if dirty:
        raise PreregistrationError(f"registered files have uncommitted changes:\n{dirty}")
    commit = _git("log", "-1", "--format=%H", "--", str(document), root=root).stdout.strip()
    if not commit:
        raise PreregistrationError("no commit contains the preregistration")
    if fetch:
        _git("fetch", "origin", "main", "--quiet", root=root)
    if _git("merge-base", "--is-ancestor", commit, "origin/main", root=root).returncode != 0:
        raise PreregistrationError(
            f"preregistration commit {commit[:12]} is not an ancestor of origin/main: "
            "push it before executing. This is mandatory."
        )
    return {
        "preregistration_document": str(document),
        "preregistration_sha256": sha256_file(doc),
        "preregistration_commit": commit,
        "pushed_to_origin_main": True,
        "definition_fingerprint": expected_fingerprint,
    }
