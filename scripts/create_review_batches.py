#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict, deque
from pathlib import Path


REVIEW_ORDER = {
    "todo": 0,
    "approved": 1,
    "approved_with_edits": 2,
    "edited": 3,
    "rejected": 4,
}

SUGGESTED_ORDER = {
    "candidate_approve": 0,
    "needs_edit": 1,
    "": 2,
}


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def interleave_by_source(rows: list[dict]) -> list[dict]:
    grouped: dict[str, deque] = defaultdict(deque)
    for row in rows:
        grouped[row.get("source_export", "")].append(row)

    ordered_sources = sorted(
        grouped.keys(),
        key=lambda key: (
            -len(grouped[key]),
            key,
        ),
    )

    out = []
    while ordered_sources:
        next_sources = []
        for source in ordered_sources:
            bucket = grouped[source]
            if bucket:
                out.append(bucket.popleft())
            if bucket:
                next_sources.append(source)
        ordered_sources = next_sources
    return out


def review_sort_key(row: dict) -> tuple:
    review_status = (row.get("review_status") or "").strip().lower() or "todo"
    suggested_status = (row.get("suggested_status") or "").strip().lower()
    return (
        REVIEW_ORDER.get(review_status, 99),
        SUGGESTED_ORDER.get(suggested_status, 99),
        row.get("draft_quality", ""),
        int(row.get("priority_rank", "9999") or 9999),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review_sheet", default="data/dataset/review_sheet.csv")
    ap.add_argument("--out_dir", default="data/dataset/review_batches")
    ap.add_argument("--batch_size", type=int, default=12)
    args = ap.parse_args()

    review_sheet = Path(args.review_sheet)
    out_dir = Path(args.out_dir)
    rows = load_rows(review_sheet)
    if not rows:
        print(f"No review rows found in {review_sheet}")
        return 0

    fieldnames = list(rows[0].keys())
    split_order = ["train", "dev", "holdout"]

    pending_rows = [
        row for row in rows if ((row.get("review_status") or "").strip().lower() or "todo") == "todo"
    ]
    candidate_rows = [row for row in pending_rows if (row.get("suggested_status") or "").strip() == "candidate_approve"]
    needs_edit_rows = [row for row in pending_rows if (row.get("suggested_status") or "").strip() == "needs_edit"]

    write_rows(out_dir / "candidate_approve_queue.csv", candidate_rows, fieldnames)
    write_rows(out_dir / "needs_edit_queue.csv", needs_edit_rows, fieldnames)
    print(f"Wrote {len(candidate_rows)} rows to {out_dir / 'candidate_approve_queue.csv'}")
    print(f"Wrote {len(needs_edit_rows)} rows to {out_dir / 'needs_edit_queue.csv'}")

    total_batches = 0
    for split in split_order:
        split_rows = [row for row in pending_rows if row.get("split") == split]
        split_rows.sort(key=review_sort_key)
        ordered = interleave_by_source(split_rows)

        for idx in range(0, len(ordered), args.batch_size):
            batch_num = idx // args.batch_size + 1
            batch_rows = ordered[idx : idx + args.batch_size]
            out_path = out_dir / f"{split}_batch_{batch_num:02d}.csv"
            write_rows(out_path, batch_rows, fieldnames)
            print(f"Wrote {len(batch_rows)} rows to {out_path}")
            total_batches += 1

    print(f"Generated {total_batches} review batch files in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
