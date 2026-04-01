#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def count_by(rows: list[dict], key: str) -> dict[str, int]:
    return dict(Counter((row.get(key) or "").strip() for row in rows))


def count_flags(rows: list[dict]) -> dict[str, int]:
    counter = Counter()
    for row in rows:
        raw = (row.get("auto_flags") or "").strip()
        if not raw:
            continue
        for flag in [part.strip() for part in raw.split(",") if part.strip()]:
            counter[flag] += 1
    return dict(counter)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review_sheet", default="data/dataset/review_sheet.csv")
    ap.add_argument(
        "--out",
        default="data/dataset/review_progress_summary.json",
        help="JSON summary output path",
    )
    args = ap.parse_args()

    rows = load_rows(Path(args.review_sheet))
    todo_rows = [row for row in rows if (row.get("review_status") or "").strip() in {"", "todo"}]
    summary = {
        "total_rows": len(rows),
        "by_status": count_by(rows, "review_status"),
        "by_suggested_status": count_by(rows, "suggested_status"),
        "by_split": count_by(rows, "split"),
        "by_quality": count_by(rows, "draft_quality"),
        "by_source_export": count_by(rows, "source_export"),
        "by_auto_flag": count_flags(rows),
        "remaining_todo": len(todo_rows),
        "todo_by_suggested_status": count_by(todo_rows, "suggested_status"),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
