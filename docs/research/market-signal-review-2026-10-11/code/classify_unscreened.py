#!/usr/bin/env python3
"""Classifier-assisted triage for the pool records whose screening batches produced no output.

Three main screening batches (300 records) and one dual batch have no decisions: their agents were stopped by a
usage limit before writing anything and their reasoning was not persisted (recovery/recovery_inventory.md). Rather
than pay for those batches again, a TF-IDF logistic regression is trained on the 2,011 records the rubric screeners
did decide, validated by 5-fold cross-validation, and applied to the 300. The batches were hash-shuffled, so the
missing records are a random 13% of the pool, not a systematic slice.

Use of the result is deliberately limited:
  * predicted include/maybe  -> carried forward to the coding stage, where each paper is read anyway;
  * predicted exclude        -> excluded ONLY if the predicted probability of relevance is below the threshold chosen so
                               that cross-validated recall of relevant records is at least 0.97. Everything else stays 'maybe'.
Every row carries provenance `classifier_assisted` so that it is never mistaken for a rubric-screened decision.

Run:  .venv/bin/python docs/research/market-signal-review-2026-10-11/code/classify_unscreened.py
Writes recovery/classifier_assisted.csv and recovery/classifier_validation.json.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def text(p: dict) -> str:
    return f"{p['title']} . {p['title']} . {(p.get('abstract') or '')[:1200]} {p.get('venue') or ''}"


def main() -> int:
    pool = {p["pool_id"]: p for p in map(json.loads, (BASE / "data/candidates_pool.jsonl").open())}
    ledger = {r["pool_id"]: r for r in csv.DictReader((BASE / "screening_log.csv").open())}
    labeled = [(pid, ledger[pid]["decision"] != "exclude") for pid in pool if ledger[pid]["decision"] in ("include", "maybe", "exclude")]
    unlabeled = [pid for pid in pool if ledger[pid]["decision"] == "not_screened"]
    X = [text(pool[pid]) for pid, _ in labeled]
    y = np.array([lab for _, lab in labeled], dtype=int)
    model = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.6, sublinear_tf=True, stop_words="english"),
        LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced"),
    )
    proba = cross_val_predict(model, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=7), method="predict_proba")[:, 1]
    auc = float(roc_auc_score(y, proba))
    # the lowest threshold giving cross-validated recall of relevant records >= 0.97
    order = np.sort(proba[y == 1])
    thr = float(order[int(np.floor(0.03 * len(order)))])
    pred_out = proba < thr
    recall = float(((~pred_out) & (y == 1)).sum() / (y == 1).sum())
    removed = float(pred_out.mean())
    model.fit(X, y)
    p_new = model.predict_proba([text(pool[pid]) for pid in unlabeled])[:, 1]
    rows = []
    for pid, pr in zip(unlabeled, p_new):
        rows.append({"pool_id": pid, "title": pool[pid]["title"], "year": pool[pid]["year"], "doi": pool[pid]["doi"],
                     "arxiv": pool[pid]["arxiv"], "seed": pool[pid].get("seed", False), "p_relevant": round(float(pr), 4),
                     "decision": "exclude_by_classifier" if (pr < thr and not pool[pid].get("seed")) else "carry_forward",
                     "provenance": "classifier_assisted"})
    with (BASE / "recovery/classifier_assisted.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: -r["p_relevant"]))
    report = {"trained_on": len(labeled), "relevant_share": float(y.mean()), "cv_auc": round(auc, 4), "threshold": round(thr, 4),
              "cv_recall_at_threshold": round(recall, 4), "cv_share_removed": round(removed, 4), "applied_to": len(unlabeled),
              "excluded_by_classifier": sum(r["decision"] == "exclude_by_classifier" for r in rows),
              "carried_forward": sum(r["decision"] == "carry_forward" for r in rows)}
    (BASE / "recovery/classifier_validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
