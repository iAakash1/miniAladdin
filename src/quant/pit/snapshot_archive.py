"""Append-only, hash-chained archive of provider snapshots: the only way to make today's provider values replayable tomorrow.

Most inputs of the live scorer (P/E, analyst targets, earnings surprise, news sentiment, macro releases) are provider answers that are overwritten the next day. Nothing in the repository kept them, so a
backtest of those factors can only use a later, revised value (`docs/research/market-signal-review-2026-10-11/05_OMNISIGNAL_SIGNAL_AUDIT.md`). This module is the storage half of fixing that. It is a
research-side library; nothing in the production service imports it.

**What it guarantees**

* Every record names its source, instrument, retrieval time (UTC, aware), optional publication time with the kind of evidence behind it, the date the payload describes, the payload schema and source
  versions, the licence and retention terms, a validation status, and the SHA-256 of the payload. A record without any of these is refused.
* Records are only ever appended. Each record carries the hash of its content and the hash of the chain up to it, so an edit, a deletion, a reordering or a truncated tail is detected by `verify()`.
  The head hash can be copied somewhere else (a commit, a log) to make a consistent rewrite of the whole archive detectable too.
* Payloads are stored once, gzip-compressed, under the hash of their bytes, and never rewritten. A payload may be purged when its retention ends; the record, and therefore the proof that the content
  existed, stays.
* A re-capture whose payload equals the latest one for the same series is a no-op (the first time the content was seen is the time it was known). Content that flips A, B, A is three records.
* `as_of(t)` returns, per series, the latest record retrieved at or before `t`. Observed captures must carry a retrieval time within a few minutes of the writer's clock and cannot go backwards, so
  history cannot be back-dated by accident; anything imported with a time the importer merely asserts is labelled `asserted` and is excluded from replays unless asked for.

**What it does not do**

It cannot reconstruct the past. History starts at the first observed capture of a series, and `as_of` before that returns nothing and says so (`coverage()`); it never back-fills, interpolates or
substitutes a later value. A publication time is only as good as its stated kind (`vendor_stated`, `first_observed`, `unknown`). It is a ledger of what this system saw, not a claim about what the market
could have seen.
"""

from __future__ import annotations

import fcntl
import gzip
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

ARCHIVE_SCHEMA_VERSION = 1
ZERO_HASH = "0" * 64
VALIDATION_STATUSES = ("unvalidated", "valid", "invalid")
PUBLISHED_KINDS = ("vendor_stated", "first_observed", "unknown")
CAPTURES = ("observed", "asserted")
REDISTRIBUTION = ("allowed", "not_allowed", "unknown")
#: An observed capture must be stamped within this window of the writer's clock.
OBSERVED_SKEW = timedelta(minutes=5)
INSTRUMENT_ID = re.compile(r"^(cik|security|figi|isin|ticker|series):\S+$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class SnapshotValidationError(ValueError):
    """The record would make the archive inconsistent or incomplete; nothing was written."""


@dataclass(frozen=True)
class SnapshotRecord:
    seq: int
    source_id: str
    instrument_id: str
    record_type: str
    retrieved_at: str
    published_at: Optional[str]
    published_kind: str
    effective_date: str
    payload_sha256: Optional[str]
    payload_bytes: Optional[int]
    reference: Optional[str]
    schema_version: str
    source_version: str
    licence: str
    redistribution: str
    retention: str
    validation_status: str
    validation_notes: str
    capture: str
    archive_schema: int
    record_id: str
    prev_hash: str
    chain_hash: str

    @property
    def series(self) -> tuple[str, str, str]:
        return (self.source_id, self.instrument_id, self.record_type)

    def retrieved(self) -> datetime:
        return _parse_utc(self.retrieved_at)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AppendResult:
    status: str                        # "appended" | "duplicate"
    record: SnapshotRecord


@dataclass
class VerifyReport:
    ok: bool
    records: int
    head: str
    problems: list[str] = field(default_factory=list)
    torn_tail: bool = False


# ── helpers ──────────────────────────────────────────────────────────────

def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_text(value: datetime, name: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SnapshotValidationError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _content(record: dict[str, Any]) -> dict[str, Any]:
    """The fields that identify a record: everything except its position in the chain."""
    return {k: v for k, v in record.items() if k not in ("seq", "record_id", "prev_hash", "chain_hash")}


def _chain(prev_hash: str, record_id: str) -> str:
    return _sha256((prev_hash + record_id).encode("ascii"))


def _retention_ok(retention: str) -> bool:
    if retention in ("indefinite", "reference_only"):
        return True
    if retention.startswith("delete_after:"):
        try:
            Date.fromisoformat(retention.split(":", 1)[1])
            return True
        except ValueError:
            return False
    return False


def _expired(retention: str, today: Date) -> bool:
    return retention.startswith("delete_after:") and Date.fromisoformat(retention.split(":", 1)[1]) < today


def check_fields(record: dict[str, Any]) -> list[str]:
    """Structural problems of a record's content (no chain, no filesystem): used on append and again on verify."""
    problems = []
    for key in ("source_id", "record_type", "schema_version", "source_version", "licence"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            problems.append(f"{key} is missing")
    if not isinstance(record.get("instrument_id"), str) or not INSTRUMENT_ID.match(record.get("instrument_id") or ""):
        problems.append("instrument_id must be namespaced (cik:, security:, figi:, isin:, ticker:, series:); a bare ticker is not an identity")
    if record.get("validation_status") not in VALIDATION_STATUSES:
        problems.append(f"validation_status must be one of {VALIDATION_STATUSES}")
    if record.get("published_kind") not in PUBLISHED_KINDS:
        problems.append(f"published_kind must be one of {PUBLISHED_KINDS}")
    if record.get("capture") not in CAPTURES:
        problems.append(f"capture must be one of {CAPTURES}")
    if record.get("redistribution") not in REDISTRIBUTION:
        problems.append(f"redistribution must be one of {REDISTRIBUTION}")
    if not _retention_ok(str(record.get("retention", ""))):
        problems.append("retention must be indefinite, reference_only or delete_after:YYYY-MM-DD")
    try:
        retrieved = _parse_utc(record["retrieved_at"])
    except (KeyError, TypeError, ValueError):
        problems.append("retrieved_at is missing or malformed")
        retrieved = None
    published = record.get("published_at")
    if published is None:
        if record.get("published_kind") != "unknown":
            problems.append("published_kind must be 'unknown' when published_at is absent")
    else:
        try:
            if retrieved is not None and _parse_utc(published) > retrieved:
                problems.append("published_at is after retrieved_at")
        except (TypeError, ValueError):
            problems.append("published_at is malformed")
        if record.get("published_kind") == "unknown":
            problems.append("published_at is present but published_kind says 'unknown'")
    try:
        Date.fromisoformat(record["effective_date"])
    except (KeyError, TypeError, ValueError):
        problems.append("effective_date is missing or not an ISO date")
    sha, size, ref = record.get("payload_sha256"), record.get("payload_bytes"), record.get("reference")
    if sha is None:
        if not ref:
            problems.append("a record without a stored payload must carry a reference")
        if record.get("retention") != "reference_only":
            problems.append("a record without a stored payload must have retention 'reference_only'")
    else:
        if not _HEX64.match(str(sha)):
            problems.append("payload_sha256 is malformed")
        if not isinstance(size, int) or size < 0:
            problems.append("payload_bytes is missing")
        if record.get("retention") == "reference_only":
            problems.append("retention 'reference_only' cannot hold a stored payload")
    return problems


class _State:
    """What an append needs to know about the archive so far: the chain tail, the latest record per series, and the newest observed retrieval time."""

    def __init__(self) -> None:
        self.seq, self.prev_hash = 0, ZERO_HASH
        self.last: Optional[SnapshotRecord] = None
        self.latest: dict[tuple[str, str, str], SnapshotRecord] = {}
        self.last_observed: Optional[datetime] = None

    def apply(self, record: SnapshotRecord) -> None:
        self.seq, self.prev_hash, self.last = record.seq + 1, record.chain_hash, record
        self.latest[record.series] = record
        if record.capture == "observed":
            self.last_observed = record.retrieved()


# ── the archive ──────────────────────────────────────────────────────────

class SnapshotArchive:
    """One archive per directory. Single writer (an advisory lock serialises appends); any number of readers."""

    def __init__(self, root: Path | str, *, clock: Optional[Callable[[], datetime]] = None) -> None:
        self.root = Path(root)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        (self.root / "segments").mkdir(parents=True, exist_ok=True)
        (self.root / "payloads").mkdir(parents=True, exist_ok=True)
        self._lock_path = self.root / ".lock"
        self._lock_path.touch(exist_ok=True)

    # storage ------------------------------------------------------------
    def _segment_files(self) -> list[Path]:
        return sorted((self.root / "segments").glob("*.jsonl"))

    def _payload_path(self, sha: str) -> Path:
        return self.root / "payloads" / sha[:2] / f"{sha}.gz"

    def _read_lines(self) -> Iterator[tuple[Path, int, str, bool]]:
        for path in self._segment_files():
            with path.open("rb") as handle:
                for number, raw in enumerate(handle, 1):
                    complete = raw.endswith(b"\n")
                    yield path, number, raw.decode("utf-8", errors="replace").rstrip("\n"), complete

    def records(self) -> Iterator[SnapshotRecord]:
        """Every readable record in chain order. Malformed or torn lines are skipped here and reported by `verify()`."""
        for path, number, text, complete in self._read_lines():
            if not complete or not text.strip():
                continue
            try:
                yield SnapshotRecord(**json.loads(text))
            except (ValueError, TypeError):
                continue

    def _tail(self) -> tuple[int, str, Optional[SnapshotRecord]]:
        state = self._scan_state()
        return state.seq, state.prev_hash, state.last

    def head(self) -> str:
        return self._tail()[1]

    # writing ------------------------------------------------------------
    def _store_payload(self, payload: bytes) -> str:
        sha = _sha256(payload)
        target = self._payload_path(sha)
        if target.exists():
            return sha
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(gzip.compress(payload, mtime=0))
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temporary, 0o444)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return sha

    def _scan_state(self) -> "_State":
        state = _State()
        for record in self.records():
            state.apply(record)
        return state

    def append(self, **row: Any) -> AppendResult:
        """Append one record, or return the existing one when the latest capture of the series has identical content. Raises `SnapshotValidationError` and writes nothing on any inconsistency."""
        return self.append_many([row])[0]

    def append_many(self, rows: list[dict[str, Any]]) -> list[AppendResult]:
        """Append a batch under one lock and one scan of the archive. Rows are validated and written in order; the first invalid row raises, and the rows before it stay written.

        Each row takes the keyword arguments below: source_id, instrument_id, record_type, effective_date, payload (bytes, or None for a reference-only record), schema_version, source_version, licence;
        optional retrieved_at (aware datetime, default now), published_at, published_kind, reference, redistribution, retention, validation_status, validation_notes, capture.
        """
        results: list[AppendResult] = []
        with self._lock_path.open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                state = self._scan_state()
                for row in rows:
                    results.append(self._append_locked(state, **row))
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return results

    def _append_locked(self, state: "_State", *, source_id: str, instrument_id: str, record_type: str, effective_date: Date | str, payload: Optional[bytes], schema_version: str, source_version: str,
                       licence: str, retrieved_at: Optional[datetime] = None, published_at: Optional[datetime] = None, published_kind: str = "unknown", reference: Optional[str] = None,
                       redistribution: str = "unknown", retention: str = "indefinite", validation_status: str = "unvalidated", validation_notes: str = "", capture: str = "observed") -> AppendResult:
        now = self._clock()
        retrieved_text = _utc_text(retrieved_at if retrieved_at is not None else now, "retrieved_at")
        if payload is None and retention == "indefinite":
            retention = "reference_only"
        record = {
            "source_id": source_id, "instrument_id": instrument_id, "record_type": record_type, "retrieved_at": retrieved_text,
            "published_at": _utc_text(published_at, "published_at") if published_at is not None else None, "published_kind": published_kind,
            "effective_date": effective_date.isoformat() if isinstance(effective_date, Date) else effective_date,
            "payload_sha256": _sha256(payload) if payload is not None else None, "payload_bytes": len(payload) if payload is not None else None, "reference": reference,
            "schema_version": schema_version, "source_version": source_version, "licence": licence, "redistribution": redistribution, "retention": retention,
            "validation_status": validation_status, "validation_notes": validation_notes, "capture": capture, "archive_schema": ARCHIVE_SCHEMA_VERSION,
        }
        problems = check_fields(record)
        if problems:
            raise SnapshotValidationError("; ".join(problems))
        retrieved = _parse_utc(retrieved_text)
        if capture == "observed" and abs(retrieved - now) > OBSERVED_SKEW:
            raise SnapshotValidationError(f"an observed capture must be stamped within {OBSERVED_SKEW} of the writer's clock (retrieved_at {retrieved_text}, clock {_utc_text(now, 'now')}); "
                                          "use capture='asserted' for imported history")
        latest = state.latest.get((source_id, instrument_id, record_type))
        if latest is not None and latest.payload_sha256 == record["payload_sha256"] and latest.effective_date == record["effective_date"] and latest.reference == reference:
            return AppendResult("duplicate", latest)
        if capture == "observed" and state.last_observed is not None and retrieved < state.last_observed:
            raise SnapshotValidationError(f"an observed capture cannot be older than the previous one ({_utc_text(state.last_observed, 'previous')})")
        if payload is not None:
            self._store_payload(payload)
        record_id = _sha256(_canonical(record))
        full = SnapshotRecord(seq=state.seq, record_id=record_id, prev_hash=state.prev_hash, chain_hash=_chain(state.prev_hash, record_id), **record)
        segment = self.root / "segments" / f"{now.astimezone(timezone.utc):%Y-%m}.jsonl"
        with segment.open("ab") as out:
            out.write(_canonical(full.as_dict()) + b"\n")
            out.flush()
            os.fsync(out.fileno())
        state.apply(full)
        return AppendResult("appended", full)

    # reading ------------------------------------------------------------
    def as_of(self, when: datetime, *, source_id: Optional[str] = None, instrument_id: Optional[str] = None, record_type: Optional[str] = None, include_asserted: bool = False) -> list[SnapshotRecord]:
        """The latest record per series retrieved at or before `when`. Series with nothing yet retrieved are absent (see `coverage()`), never filled with a later value."""
        if when.tzinfo is None:
            raise SnapshotValidationError("when must be timezone-aware")
        cutoff = when.astimezone(timezone.utc)
        best: dict[tuple[str, str, str], SnapshotRecord] = {}
        for record in self.records():
            if (source_id and record.source_id != source_id) or (instrument_id and record.instrument_id != instrument_id) or (record_type and record.record_type != record_type):
                continue
            if record.capture == "asserted" and not include_asserted:
                continue
            if record.retrieved() > cutoff:
                continue
            current = best.get(record.series)
            if current is None or (record.retrieved(), record.seq) >= (current.retrieved(), current.seq):
                best[record.series] = record
        return [best[key] for key in sorted(best)]

    def payload(self, record: SnapshotRecord) -> bytes:
        """The stored bytes, re-checked against the record's hash. Raises if purged, missing or altered."""
        if record.payload_sha256 is None:
            raise FileNotFoundError("reference-only record: no payload was stored")
        if not _HEX64.match(record.payload_sha256):
            raise SnapshotValidationError("payload hash is malformed")
        path = self._payload_path(record.payload_sha256)
        if not path.exists():
            raise FileNotFoundError("payload purged or missing")
        data = gzip.decompress(path.read_bytes())
        if _sha256(data) != record.payload_sha256:
            raise SnapshotValidationError(f"payload for record {record.seq} does not match its recorded hash")
        return data

    def coverage(self) -> dict[str, dict[str, Any]]:
        """First and last observed retrieval per source, and the number of series and records: the span over which `as_of` can answer at all."""
        out: dict[str, dict[str, Any]] = {}
        for record in self.records():
            if record.capture != "observed":
                continue
            entry = out.setdefault(record.source_id, {"first_observed": record.retrieved_at, "last_observed": record.retrieved_at, "records": 0, "series": set()})
            entry["last_observed"] = max(entry["last_observed"], record.retrieved_at)
            entry["first_observed"] = min(entry["first_observed"], record.retrieved_at)
            entry["records"] += 1
            entry["series"].add((record.instrument_id, record.record_type))
        return {k: {**v, "series": len(v["series"])} for k, v in sorted(out.items())}

    def anchor(self) -> dict[str, Any]:
        """A small statement to store outside the archive (a commit, a log): the head hash and the record count at this moment."""
        seq, head, _ = self._tail()
        return {"records": seq, "head": head, "at": _utc_text(self._clock(), "now")}

    # integrity ----------------------------------------------------------
    def verify(self, *, today: Optional[Date] = None) -> VerifyReport:
        today = today or self._clock().date()
        problems: list[str] = []
        torn = False
        expected_seq, prev_hash, count = 0, ZERO_HASH, 0
        last_observed: Optional[datetime] = None
        for path, number, text, complete in self._read_lines():
            where = f"{path.name}:{number}"
            if not complete:
                torn = True
                problems.append(f"{where}: torn tail (line without a terminating newline)")
                continue
            if not text.strip():
                problems.append(f"{where}: empty line")
                continue
            try:
                raw = json.loads(text)
                record = SnapshotRecord(**raw)
            except (ValueError, TypeError) as error:
                problems.append(f"{where}: unreadable record ({type(error).__name__})")
                continue
            count += 1
            if record.seq != expected_seq:
                problems.append(f"{where}: sequence {record.seq}, expected {expected_seq}")
            if record.prev_hash != prev_hash:
                problems.append(f"{where}: chain broken (prev_hash does not match the previous record)")
            content = _content(raw)
            if _sha256(_canonical(content)) != record.record_id:
                problems.append(f"{where}: record content does not match its record_id (edited)")
            if _chain(record.prev_hash, record.record_id) != record.chain_hash:
                problems.append(f"{where}: chain_hash does not match")
            problems.extend(f"{where}: {p}" for p in check_fields(content))
            if record.capture == "observed":
                if last_observed is not None and record.retrieved() < last_observed:
                    problems.append(f"{where}: observed capture goes back in time")
                last_observed = record.retrieved()
            if record.payload_sha256 and _HEX64.match(record.payload_sha256):
                path_ = self._payload_path(record.payload_sha256)
                if not path_.exists():
                    if not _expired(record.retention, today):
                        problems.append(f"{where}: payload {record.payload_sha256[:12]} is missing")
                else:
                    try:
                        data = gzip.decompress(path_.read_bytes())
                    except (OSError, EOFError):
                        problems.append(f"{where}: payload {record.payload_sha256[:12]} is not readable")
                    else:
                        if _sha256(data) != record.payload_sha256:
                            problems.append(f"{where}: payload {record.payload_sha256[:12]} does not match its hash (corrupted)")
                        elif len(data) != record.payload_bytes:
                            problems.append(f"{where}: payload size differs from the record")
            prev_hash, expected_seq = record.chain_hash, record.seq + 1
        return VerifyReport(ok=not problems, records=count, head=prev_hash, problems=problems, torn_tail=torn)

    def expire_payloads(self, today: Optional[Date] = None) -> list[str]:
        """Delete payload files whose retention has ended for every record that shares them, keeping all records (and so their hashes). Returns the hashes removed."""
        today = today or self._clock().date()
        holders: dict[str, list[bool]] = {}
        for record in self.records():
            if record.payload_sha256 and _HEX64.match(record.payload_sha256):
                holders.setdefault(record.payload_sha256, []).append(_expired(record.retention, today))
        removed = []
        for sha, flags in sorted(holders.items()):
            path = self._payload_path(sha)
            if all(flags) and path.exists():
                os.chmod(path, 0o644)
                path.unlink()
                removed.append(sha)
        return removed
