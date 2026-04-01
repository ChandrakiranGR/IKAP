#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


VALID_STATUSES = {"approved", "approved_with_edits", "edited"}
FORMAT_MARKERS = [
    "Category:",
    "Clarifying question:",
    "Steps:",
    "References:",
    "If this does not resolve your issue: Contact Northeastern IT Support and include:",
]


def load_review_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Review sheet not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def normalize_status(value: str) -> str:
    return (value or "").strip().lower()


def format_ok(answer: str) -> bool:
    return all(marker in (answer or "") for marker in FORMAT_MARKERS)


def build_example(row: dict) -> dict:
    question = (row.get("edited_question") or row.get("question") or "").strip()
    answer = (row.get("edited_answer") or row.get("draft_answer") or "").strip()
    return {
        "messages": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def stable_key(row: dict) -> str:
    seed = "|".join(
        [
            row.get("source_export", ""),
            row.get("article_id", ""),
            row.get("id", ""),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review_sheet", default="data/dataset/review_sheet.csv")
    ap.add_argument("--out_dir", default="data/finetune")
    ap.add_argument(
        "--prefix",
        default="production",
        help="Output file prefix, e.g. production -> production_train.jsonl",
    )
    args = ap.parse_args()

    review_rows = load_review_rows(Path(args.review_sheet))
    out_dir = Path(args.out_dir)

    approved_rows = []
    issues = []
    for row in review_rows:
        status = normalize_status(row.get("review_status", ""))
        if status not in VALID_STATUSES:
            continue

        example = build_example(row)
        question = example["messages"][0]["content"]
        answer = example["messages"][1]["content"]

        if not question or not answer:
            issues.append(
                {
                    "article_id": row.get("article_id", ""),
                    "id": row.get("id", ""),
                    "issue": "missing_question_or_answer",
                }
            )
            continue
        if not format_ok(answer):
            issues.append(
                {
                    "article_id": row.get("article_id", ""),
                    "id": row.get("id", ""),
                    "issue": "invalid_answer_format",
                }
            )
            continue

        approved_rows.append(row)

    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in approved_rows:
        by_source[row.get("source_export", "")].append(row)

    dev_keys: set[str] = set()
    for source, rows in by_source.items():
        ordered = sorted(rows, key=stable_key)
        # Keep one validation example per source export when possible.
        dev_keys.add(ordered[0]["id"])

    train_rows = []
    dev_rows = []
    manifest_rows = []

    for row in approved_rows:
        example = build_example(row)
        split = "dev" if row["id"] in dev_keys else "train"
        if split == "dev":
            dev_rows.append(example)
        else:
            train_rows.append(example)

        manifest_rows.append(
            {
                "id": row.get("id", ""),
                "article_id": row.get("article_id", ""),
                "title": row.get("title", ""),
                "source_export": row.get("source_export", ""),
                "assigned_split": split,
                "review_status": row.get("review_status", ""),
            }
        )

    prefix = args.prefix
    write_jsonl(out_dir / f"{prefix}_train.jsonl", train_rows)
    write_jsonl(out_dir / f"{prefix}_dev.jsonl", dev_rows)
    write_csv(out_dir / f"{prefix}_dataset_manifest.csv", manifest_rows)
    write_csv(
        out_dir / f"{prefix}_dataset_issues.csv",
        issues or [{"article_id": "", "id": "", "issue": ""}],
    )

    summary = {
        "review_sheet": args.review_sheet,
        "approved_statuses": sorted(VALID_STATUSES),
        "train_examples": len(train_rows),
        "dev_examples": len(dev_rows),
        "issues": len(issues),
        "sources_in_dev": dict(Counter(row["source_export"] for row in approved_rows if row["id"] in dev_keys)),
        "uses_all_approved_examples": True,
        "note": "This production dataset reuses examples that were previously reserved from the benchmark holdout. Historical benchmark comparisons should be treated separately.",
    }
    (out_dir / f"{prefix}_dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Train examples: {len(train_rows)}")
    print(f"Dev examples: {len(dev_rows)}")
    print(f"Issues: {len(issues)}")
    print(f"Wrote outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
