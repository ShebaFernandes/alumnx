"""Evaluation harness.

Usage:
  1. Put inbox.json (or any email batch) in this folder.
  2. Hand-label at least 50 emails in labels.csv (see labels.example.csv) with
     columns: email_id, true_category, true_assignee, should_create.
  3. Run:  python evals/run_eval.py --emails inbox.json --labels evals/labels.csv
     (needs GEMINI_API_KEY set to exercise the real classifier).

It routes each labelled email through the SAME routing.route_email used in
production, aligns predictions to your labels, and prints precision/recall/F1
per category plus the four grading buckets (correct/misrouted/missed/spurious).
Paste the output into EVALS.md.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.routing import route_email  # noqa: E402
from app.schemas import Email  # noqa: E402


def load_emails(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    arr = data if isinstance(data, list) else data.get("emails", [])
    return {e["email_id"]: Email(**e) for e in arr}


def load_labels(path):
    labels = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["email_id"].strip()] = {
                "category": (row.get("true_category") or "").strip(),
                "assignee": (row.get("true_assignee") or "").strip(),
                "should_create": (row.get("should_create") or "").strip().lower() in ("1", "true", "yes", "y"),
            }
    return labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emails", required=True)
    ap.add_argument("--labels", required=True)
    args = ap.parse_args()

    emails = load_emails(args.emails)
    labels = load_labels(args.labels)

    # Per-category confusion for precision/recall.
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)

    buckets = {"correct": 0, "misrouted": 0, "missed": 0, "spurious": 0}
    rows = []

    for eid, label in labels.items():
        email = emails.get(eid)
        if email is None:
            print(f"! label for {eid} has no matching email, skipping")
            continue
        decision = route_email(email)
        predicted_create = decision.action == "create"
        pred_cat = decision.category if predicted_create else None
        pred_assignee = decision.assignee_id if predicted_create else None

        # Grading buckets.
        if not label["should_create"] and predicted_create:
            buckets["spurious"] += 1
        elif label["should_create"] and not predicted_create:
            buckets["missed"] += 1
        elif label["should_create"] and predicted_create:
            if pred_assignee == label["assignee"]:
                buckets["correct"] += 1
            else:
                buckets["misrouted"] += 1

        # Precision/recall on category (only where a task should exist).
        if label["should_create"]:
            true_cat = label["category"]
            if pred_cat == true_cat:
                tp[true_cat] += 1
            else:
                fn[true_cat] += 1
                if pred_cat:
                    fp[pred_cat] += 1
        elif predicted_create and pred_cat:
            fp[pred_cat] += 1  # created when it shouldn't have

        rows.append((eid, label["assignee"], pred_assignee, label["category"], pred_cat))

    print("\n=== Grading buckets ===")
    total = sum(buckets.values())
    for k, v in buckets.items():
        print(f"  {k:10s}: {v}")
    print(f"  total     : {total}")

    print("\n=== Precision / Recall / F1 per category ===")
    cats = set(list(tp) + list(fp) + list(fn))
    print(f"  {'category':16s} {'P':>6} {'R':>6} {'F1':>6}  (tp/fp/fn)")
    for c in sorted(cats):
        p = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        r = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        print(f"  {c:16s} {p:6.2f} {r:6.2f} {f1:6.2f}  ({tp[c]}/{fp[c]}/{fn[c]})")

    print("\n=== Disagreements (label -> predicted) ===")
    for eid, ta, pa, tc, pc in rows:
        if ta != pa:
            print(f"  {eid}: assignee {ta} -> {pa} | category {tc} -> {pc}")


if __name__ == "__main__":
    main()
