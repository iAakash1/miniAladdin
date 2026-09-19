"""The Kaggle export/import path: refusal without licence acknowledgement, independent worker partitions, rejected imports."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.quant import export_kaggle_experiment as X
from src.quant.study import exp010a, exp011 as E

REPO = Path(__file__).resolve().parents[2]


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=REPO, capture_output=True, text=True)


def test_export_refuses_without_the_licence_acknowledgement_and_writes_nothing(tmp_path):
    out = tmp_path / "bundle"
    result = run("-m", "scripts.quant.export_kaggle_experiment", "--experiment", "EXP-011", "--out", str(out))
    assert result.returncode != 0 and "REFUSED" in (result.stderr + result.stdout)
    assert not out.exists()


def test_export_only_knows_the_registered_experiment(tmp_path):
    result = run("-m", "scripts.quant.export_kaggle_experiment", "--experiment", "EXP-999", "--out", str(tmp_path / "x"))
    assert result.returncode != 0


def test_worker_partitions_are_independent_and_cover_every_seed_once():
    parts = X.partition(list(range(10)), 2)
    assert parts == [[0, 2, 4, 6, 8], [1, 3, 5, 7, 9]]
    flat = sorted(s for p in parts for s in p)
    assert flat == list(range(10)) and len(set(parts[0]) & set(parts[1])) == 0


def synthetic_predictions(seed=3):
    rng = np.random.default_rng(seed)
    rows = [(date(2018, 1, 1 + i % 28), f"S{j:02d}", i % 8, rng.uniform(-1, 1), rng.normal()) for i in range(80) for j in range(12)]
    return pd.DataFrame(rows, columns=["date", "symbol", "fold", E.LABEL, "prediction"])


def write_result(directory, arm, seed, predictions, **receipt_overrides):
    directory.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(directory / f"{arm}_seed_{seed:02d}_predictions.parquet", index=False)
    receipt = {"experiment_id": "EXP-011", "arm": arm, "seed": seed, "definition_fingerprint": E.definition_fingerprint(REPO),
               "rich_dataset_id": E.RICH_DATASET_ID, "rich_content_hash": E.RICH_CONTENT_HASH, "rich_feature_hash": E.RICH_FEATURE_HASH,
               "folds": 8, "prediction_sha256": exp010a._prediction_hash(predictions), "git_commit": "abc", "device": "cpu", "fit_seconds": 1.0,
               "dependency_versions": json.loads((REPO / "experiments/EXP-010A/manifest.json").read_text())["dependency_versions"]}
    receipt.update(receipt_overrides)
    (directory / f"{arm}_seed_{seed:02d}.json").write_text(json.dumps(receipt))


def test_import_accepts_a_verified_result_and_rejects_every_mismatch(tmp_path):
    good, bad, output = tmp_path / "good", tmp_path / "bad", tmp_path / "experiment"
    write_result(good, "E3", 3, synthetic_predictions())
    ok = run("-m", "scripts.quant.import_kaggle_results", "--results", str(good), "--output-dir", str(output))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert (output / "checkpoints" / "E3_seed_03_predictions.parquet").exists()
    for index, change in enumerate(({"definition_fingerprint": "0" * 64}, {"rich_content_hash": "0" * 64}, {"prediction_sha256": "0" * 64},
                                    {"rich_feature_hash": "0" * 64}, {"device": ""})):
        write_result(bad / str(index), "E3", 4, synthetic_predictions(4), **change)
    other = tmp_path / "rejected_output"
    rejected = run("-m", "scripts.quant.import_kaggle_results", "--results", *[str(bad / str(i)) for i in range(5)], "--output-dir", str(other))
    assert rejected.returncode == 1
    report = json.loads((other / "import_report.json").read_text())
    assert report["accepted"] == [] and len(report["rejected"]) == 5
    assert not (other / "checkpoints").exists()


def test_import_refuses_unregistered_arms_seeds_and_the_frozen_arm(tmp_path):
    results, output = tmp_path / "r", tmp_path / "o"
    write_result(results, "E2", 0, synthetic_predictions())      # E2 is the frozen EXP-010A; never imported
    write_result(results, "E3", 11, synthetic_predictions())     # seed outside 0-9
    result = run("-m", "scripts.quant.import_kaggle_results", "--results", str(results), "--output-dir", str(output))
    assert result.returncode == 1
    assert json.loads((output / "import_report.json").read_text())["accepted"] == []
