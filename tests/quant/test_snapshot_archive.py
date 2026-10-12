"""The point-in-time snapshot archive: append-only chain, as-of replay, timestamp consistency, corruption detection, required fields, determinism."""

import gzip
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from src.quant.pit.snapshot_archive import SnapshotArchive, SnapshotValidationError, check_fields

T0 = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def archive(tmp_path, clock=None):
    clock = clock or Clock()
    return SnapshotArchive(tmp_path / "arch", clock=clock), clock


def row(payload=b'{"pe": 21.4}', **kw):
    base = dict(source_id="vendor.fundamentals", instrument_id="cik:0000320193", record_type="fundamentals", effective_date=date(2026, 3, 2), payload=payload, schema_version="v1",
                source_version="2026-03", licence="vendor-terms-no-redistribution", redistribution="not_allowed", validation_status="valid")
    base.update(kw)
    return base


def test_append_then_replay_as_of_never_shows_the_future(tmp_path):
    a, clock = archive(tmp_path)
    a.append(**row(b'{"pe": 20}'))
    clock.advance(days=1)
    a.append(**row(b'{"pe": 21}', effective_date=date(2026, 3, 3)))
    clock.advance(days=1)
    a.append(**row(b'{"pe": 22}', effective_date=date(2026, 3, 4)))
    seen = {when: [json.loads(a.payload(r))["pe"] for r in a.as_of(when)] for when in (T0, T0 + timedelta(hours=23), T0 + timedelta(days=1), T0 + timedelta(days=5))}
    assert seen == {T0: [20], T0 + timedelta(hours=23): [20], T0 + timedelta(days=1): [21], T0 + timedelta(days=5): [22]}
    assert a.as_of(T0 - timedelta(seconds=1)) == []                                        # before the first capture: nothing, never a later value
    assert a.coverage()["vendor.fundamentals"]["first_observed"].startswith("2026-03-02T14:30")


def test_identical_recapture_is_a_noop_but_a_flip_flop_is_three_records(tmp_path):
    a, clock = archive(tmp_path)
    first = a.append(**row(b"A"))
    clock.advance(hours=1)
    again = a.append(**row(b"A"))
    assert (first.status, again.status) == ("appended", "duplicate") and again.record.seq == first.record.seq
    clock.advance(hours=1)
    a.append(**row(b"B"))
    clock.advance(hours=1)
    a.append(**row(b"A"))                                                                  # content returned to an earlier value: a new fact about what was known now
    assert [r.seq for r in a.records()] == [0, 1, 2]
    assert a.payload(a.as_of(clock.now)[0]) == b"A"
    assert a.verify().ok


def test_timestamp_consistency_is_enforced(tmp_path):
    a, clock = archive(tmp_path)
    with pytest.raises(SnapshotValidationError, match="published_at is after retrieved_at"):
        a.append(**row(published_at=T0 + timedelta(minutes=1), published_kind="vendor_stated"))
    with pytest.raises(SnapshotValidationError, match="timezone-aware"):
        a.append(**row(retrieved_at=datetime(2026, 3, 2, 14, 30)))
    with pytest.raises(SnapshotValidationError, match="timezone-aware"):
        a.append(**row(published_at=datetime(2026, 3, 2, 14, 0), published_kind="vendor_stated"))
    with pytest.raises(SnapshotValidationError, match="published_kind"):
        a.append(**row(published_at=T0 - timedelta(hours=1), published_kind="unknown"))
    with pytest.raises(SnapshotValidationError, match="writer's clock"):                    # a live capture cannot be back-dated
        a.append(**row(retrieved_at=T0 - timedelta(days=30)))
    with pytest.raises(SnapshotValidationError, match="writer's clock"):                    # nor stamped in the future
        a.append(**row(retrieved_at=T0 + timedelta(hours=2)))
    assert list(a.records()) == []                                                         # nothing was written by any failed attempt
    ok = a.append(**row(published_at=T0 - timedelta(hours=3), published_kind="vendor_stated"))
    assert ok.record.published_kind == "vendor_stated"


def test_observed_captures_cannot_go_backwards_and_asserted_ones_are_labelled(tmp_path):
    a, clock = archive(tmp_path)
    a.append(**row(b"1", instrument_id="cik:1"))
    clock.advance(minutes=3)
    a.append(**row(b"2", instrument_id="cik:2"))
    with pytest.raises(SnapshotValidationError, match="older than the previous"):
        a.append(**row(b"3", instrument_id="cik:3", retrieved_at=T0 + timedelta(minutes=1)))
    # imported history: allowed with an old time, but marked asserted and excluded from replays by default
    a.append(**row(b"old", instrument_id="cik:9", retrieved_at=datetime(2019, 6, 3, tzinfo=timezone.utc), capture="asserted"))
    assert [r.instrument_id for r in a.as_of(clock.now)] == ["cik:1", "cik:2"]
    assert [r.instrument_id for r in a.as_of(clock.now, include_asserted=True)] == ["cik:1", "cik:2", "cik:9"]
    assert "cik:9" not in json.dumps(a.coverage())                                         # coverage counts only what this system saw itself
    assert a.verify().ok


@pytest.mark.parametrize("change, message", [
    ({"licence": ""}, "licence is missing"),
    ({"source_version": " "}, "source_version is missing"),
    ({"schema_version": ""}, "schema_version is missing"),
    ({"instrument_id": "AAPL"}, "namespaced"),
    ({"instrument_id": "ticker:"}, "namespaced"),
    ({"validation_status": "ok"}, "validation_status"),
    ({"retention": "forever"}, "retention"),
    ({"retention": "delete_after:soon"}, "retention"),
    ({"effective_date": "2026-13-01"}, "effective_date"),
    ({"redistribution": "maybe"}, "redistribution"),
    ({"capture": "guessed"}, "capture"),
    ({"payload": None}, "reference"),                                                      # no payload and no reference: nothing to point at
])
def test_records_with_missing_or_invalid_fields_are_refused(tmp_path, change, message):
    a, _ = archive(tmp_path)
    with pytest.raises(SnapshotValidationError, match=message):
        a.append(**row(**change))
    assert list(a.records()) == []


def test_reference_only_record_needs_a_reference_and_stores_no_payload(tmp_path):
    a, _ = archive(tmp_path)
    result = a.append(**row(payload=None, reference="https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/", licence="public-domain", redistribution="allowed"))
    assert result.record.payload_sha256 is None and result.record.retention == "reference_only"
    with pytest.raises(FileNotFoundError):
        a.payload(result.record)
    assert not any((a.root / "payloads").rglob("*.gz")) and a.verify().ok


def test_a_corrupted_payload_is_detected_on_verify_and_on_read(tmp_path):
    a, _ = archive(tmp_path)
    record = a.append(**row(b"important numbers")).record
    path = a._payload_path(record.payload_sha256)
    path.chmod(0o644)
    path.write_bytes(gzip.compress(b"tampered numbers!"))                                  # same length would not matter: the hash does
    report = a.verify()
    assert not report.ok and any("corrupted" in p for p in report.problems)
    with pytest.raises(SnapshotValidationError):
        a.payload(record)


def test_an_edited_record_a_deleted_record_and_a_torn_tail_are_detected(tmp_path):
    a, clock = archive(tmp_path)
    for i in range(4):
        a.append(**row(f"v{i}".encode(), instrument_id=f"cik:{i}"))
        clock.advance(minutes=1)
    segment = next((a.root / "segments").glob("*.jsonl"))
    original = segment.read_text()
    lines = original.splitlines()

    edited = json.loads(lines[1])
    edited["licence"] = "CC0"                                                              # quietly relicensing a record
    segment.write_text("\n".join([lines[0], json.dumps(edited, sort_keys=True, separators=(",", ":")), *lines[2:]]) + "\n")
    assert any("edited" in p for p in a.verify().problems)

    segment.write_text("\n".join([lines[0], lines[2], lines[3]]) + "\n")                   # deleting a record
    problems = a.verify().problems
    assert any("sequence" in p for p in problems) and any("chain broken" in p for p in problems)

    segment.write_text(original.rstrip("\n"))                                              # last newline lost: a torn append
    report = a.verify()
    assert report.torn_tail and not report.ok

    segment.write_text(original)
    assert a.verify().ok and a.verify().records == 4


def test_a_missing_payload_is_a_problem_unless_its_retention_has_ended(tmp_path):
    a, clock = archive(tmp_path)
    keep = a.append(**row(b"keep", instrument_id="cik:1")).record
    temp = a.append(**row(b"temporary", instrument_id="cik:2", retention="delete_after:2026-06-30")).record
    clock.advance(minutes=1)
    a._payload_path(temp.payload_sha256).chmod(0o644)
    a._payload_path(temp.payload_sha256).unlink()
    assert not a.verify(today=date(2026, 6, 1)).ok                                         # still inside retention: the payload should be there
    assert a.verify(today=date(2026, 7, 1)).ok                                             # purged after retention: record and hash remain, which is the point
    a._payload_path(keep.payload_sha256).chmod(0o644)
    a._payload_path(keep.payload_sha256).unlink()
    assert any("missing" in p for p in a.verify(today=date(2026, 7, 1)).problems)


def test_expire_payloads_keeps_content_still_needed_by_another_record(tmp_path):
    a, clock = archive(tmp_path)
    a.append(**row(b"shared", instrument_id="cik:1", retention="delete_after:2026-04-01"))
    kept = a.append(**row(b"shared", instrument_id="cik:2")).record                        # same bytes, indefinite retention
    solo = a.append(**row(b"solo", instrument_id="cik:3", retention="delete_after:2026-04-01")).record
    removed = a.expire_payloads(today=date(2026, 5, 1))
    assert removed == [solo.payload_sha256]
    assert a.payload(kept) == b"shared" and a.verify(today=date(2026, 5, 1)).ok


def test_a_tampered_payload_hash_cannot_make_verify_read_outside_the_archive(tmp_path):
    a, _ = archive(tmp_path)
    a.append(**row(b"x"))
    segment = next((a.root / "segments").glob("*.jsonl"))
    record = json.loads(segment.read_text().splitlines()[0])
    record["payload_sha256"] = "../../../../etc/hosts"
    segment.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    problems = a.verify().problems
    assert any("malformed" in p for p in problems) and not any("hosts" in p for p in problems if "does not match" in p)


def test_same_inputs_give_byte_identical_archives_and_the_same_head(tmp_path):
    def build(name):
        clock = Clock()
        arch = SnapshotArchive(tmp_path / name, clock=clock)
        arch.append_many([row(b"a", instrument_id="cik:1"), row(b"b", instrument_id="cik:2")])
        clock.advance(days=1)
        arch.append_many([row(b"a2", instrument_id="cik:1"), row(b"b", instrument_id="cik:2")])           # the second is a duplicate
        return arch

    one, two = build("one"), build("two")
    assert one.head() == two.head() and one.anchor()["records"] == 3
    assert (next((one.root / "segments").glob("*.jsonl"))).read_bytes() == (next((two.root / "segments").glob("*.jsonl"))).read_bytes()
    when = T0 + timedelta(days=2)
    assert [r.as_dict() for r in one.as_of(when)] == [r.as_dict() for r in two.as_of(when)]
    assert one.verify().ok and one.verify().head == one.head()


def test_the_chain_continues_across_monthly_segments(tmp_path):
    a, clock = archive(tmp_path)
    a.append(**row(b"march"))
    clock.advance(days=40)
    a.append(**row(b"april", effective_date=date(2026, 4, 11)))
    assert len(list((a.root / "segments").glob("*.jsonl"))) == 2
    report = a.verify()
    assert report.ok and report.records == 2
    assert [r.seq for r in a.records()] == [0, 1] and list(a.records())[1].prev_hash == list(a.records())[0].chain_hash


def test_check_fields_is_the_single_definition_of_a_complete_record():
    complete = dict(source_id="s", instrument_id="cik:1", record_type="t", retrieved_at="2026-03-02T14:30:00.000000Z", published_at=None, published_kind="unknown", effective_date="2026-03-02",
                    payload_sha256="a" * 64, payload_bytes=3, reference=None, schema_version="v", source_version="v", licence="l", redistribution="unknown", retention="indefinite",
                    validation_status="valid", validation_notes="", capture="observed", archive_schema=1)
    assert check_fields(complete) == []
    for key in ("source_id", "licence", "retrieved_at", "effective_date", "payload_bytes"):
        broken = {k: v for k, v in complete.items() if k != key}
        assert check_fields(broken), key
