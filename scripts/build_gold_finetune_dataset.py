#!/usr/bin/env python3
import argparse
import csv
import json
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
        "id": row["id"],
        "article_id": row["article_id"],
        "title": row["title"],
        "split": row["split"],
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
    args = ap.parse_args()

    review_rows = load_review_rows(Path(args.review_sheet))
    out_dir = Path(args.out_dir)

    train_rows = []
    dev_rows = []
    holdout_rows = []
    issues = []

    for row in review_rows:
        status = normalize_status(row.get("review_status", ""))
        if status not in VALID_STATUSES:
            continue

        example = build_example(row)
        answer = example["messages"][1]["content"]
        question = example["messages"][0]["content"]

        if not question or not answer:
            issues.append(
                {
                    "id": row["id"],
                    "article_id": row["article_id"],
                    "split": row["split"],
                    "issue": "missing_question_or_answer",
                }
            )
            continue

        if not format_ok(answer):
            issues.append(
                {
                    "id": row["id"],
                    "article_id": row["article_id"],
                    "split": row["split"],
                    "issue": "invalid_answer_format",
                }
            )
            continue

        if row["split"] == "holdout":
            holdout_rows.append(example)
        elif row["split"] == "dev":
            dev_rows.append(example)
        else:
            train_rows.append(example)

    write_jsonl(out_dir / "gold_train.jsonl", train_rows)
    write_jsonl(out_dir / "gold_dev.jsonl", dev_rows)
    write_jsonl(out_dir / "gold_holdout.jsonl", holdout_rows)
    write_csv(out_dir / "gold_dataset_issues.csv", issues or [{"id": "", "article_id": "", "split": "", "issue": ""}])

    summary = {
        "review_sheet": args.review_sheet,
        "approved_statuses": sorted(VALID_STATUSES),
        "train_examples": len(train_rows),
        "dev_examples": len(dev_rows),
        "holdout_examples": len(holdout_rows),
        "issues": len(issues),
    }
    (out_dir / "gold_dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Train examples: {len(train_rows)}")
    print(f"Dev examples: {len(dev_rows)}")
    print(f"Holdout examples: {len(holdout_rows)}")
    print(f"Issues: {len(issues)}")
    print(f"Wrote outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
