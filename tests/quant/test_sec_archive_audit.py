"""SEC archive verification: continuity, size/hash claims, members, CRC, and acceptance ranges."""

import json
import zipfile

import pandas as pd
import pytest

from src.quant.pit import sec_archive_audit as A
from src.quant.pit.sec_foundation import sha256_file

SUB = "adsh\tcik\taccepted\tform\n0001-20-000001\t1\t2020-02-10 09:00:00.0\t10-K\n0001-20-000002\t2\t2020-03-20 17:00:00.0\t10-Q\n"


def make_zip(path, members=("sub.txt", "num.txt", "tag.txt", "pre.txt"), sub=SUB):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in members:
            archive.writestr(name, sub if name == "sub.txt" else "x\ty\n1\t2\n")
    return path


def test_quarter_continuity_reports_gaps_and_duplicates():
    assert A.quarter_continuity(["2011q1.zip", "2011q2.zip", "2011q3.zip"])["continuous"]
    gap = A.quarter_continuity(["2011q1.zip", "2011q4.zip"])
    assert gap["missing"] == ["2011q2.zip", "2011q3.zip"] and not gap["continuous"]
    assert A.quarter_continuity(["2011q4.zip", "2012q1.zip"])["continuous"]


def test_expected_archive_list_is_the_58_quarters():
    names = A.expected_quarters()
    assert len(names) == 58 and names[0] == "2011q1.zip" and names[-1] == "2025q2.zip"


def test_a_good_archive_passes_and_records_its_acceptance_range(tmp_path):
    path = make_zip(tmp_path / "2020q1.zip")
    recorded = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    row = A.audit_archive(path, recorded)
    assert row["problems"] == [] and row["sub_rows"] == 2 and row["crc_ok"] is True
    assert row["accepted_min"].startswith("2020-02-10") and row["accepted_outside_quarter_share"] == 0.0


def test_hash_size_and_membership_problems_are_caught(tmp_path):
    path = make_zip(tmp_path / "2020q1.zip")
    bad = A.audit_archive(path, {"bytes": 1, "sha256": "0" * 64})
    assert "SIZE_DIFFERS_FROM_MANIFEST" in bad["problems"] and "SHA256_DIFFERS_FROM_MANIFEST" in bad["problems"]
    missing = A.audit_archive(make_zip(tmp_path / "2020q2.zip", members=("sub.txt", "num.txt")), None)
    assert any(p.startswith("MISSING_MEMBERS") for p in missing["problems"]) and "NOT_IN_MANIFEST" in missing["problems"]
    assert A.audit_archive(tmp_path / "2020q3.zip", None)["problems"] == ["MISSING"]


def test_a_corrupted_archive_fails_crc_or_zip_validation(tmp_path):
    path = make_zip(tmp_path / "2020q1.zip")
    data = bytearray(path.read_bytes())
    data[60] ^= 0xFF
    path.write_bytes(bytes(data))
    row = A.audit_archive(path, None)
    assert row["problems"], "a flipped byte must be detected"


def test_acceptance_outside_the_quarter_is_measured(tmp_path):
    sub = "adsh\tcik\taccepted\tform\na\t1\t2019-06-01 09:00:00.0\t10-K\nb\t2\t2020-02-01 09:00:00.0\t10-K\n"
    row = A.audit_archive(make_zip(tmp_path / "2020q1.zip", sub=sub), None)
    assert row["accepted_outside_quarter_share"] == 0.5


def test_verify_archives_fails_on_a_missing_quarter_and_passes_source_check_offline(tmp_path):
    manifest = {"archives": []}
    for name in A.expected_quarters()[:3]:
        path = make_zip(tmp_path / name)
        manifest["archives"].append({"filename": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    report = A.verify_archives(tmp_path, tmp_path / "manifest.json", check_source=False, progress=None)
    assert report["status"] == "FAIL" and report["present_archives"] == 3 and report["expected_archives"] == 58
    assert any(p["problems"] == ["MISSING"] for p in report["problems"])
