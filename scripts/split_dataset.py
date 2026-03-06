#!/usr/bin/env python3
import json
import random
from pathlib import Path
from collections import defaultdict, Counter

INP = Path("data/dataset/all.jsonl")
OUT_DIR = Path("data/dataset/splits")

SEED = 42


def load_rows():
    rows = []
    for line in INP.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def alloc(n: int):
    """
    Bucket split that avoids empty dev/test for small buckets.
    n>=5: 70/15/15-ish
    n=4: 2/1/1
    n=3: 1/1/1
    n=2: 1/0/1
    n=1: 1/0/0
    """
    if n >= 5:
        n_train = int(0.70 * n)
        n_dev = int(0.15 * n)
        n_test = n - n_train - n_dev
        return n_train, n_dev, n_test
    if n == 4:
        return 2, 1, 1
    if n == 3:
        return 1, 1, 1
    if n == 2:
        return 1, 0, 1
    return 1, 0, 0


def main():
    if not INP.exists():
        raise SystemExit(f"Missing {INP}")

    rows = load_rows()
    random.seed(SEED)

    # stratify by (use_case, case_type)
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["use_case"], r["case_type"])].append(r)

    train, dev, test = [], [], []
    for key, items in buckets.items():
        random.shuffle(items)
        n = len(items)
        n_train, n_dev, n_test = alloc(n)

        train.extend(items[:n_train])
        dev.extend(items[n_train : n_train + n_dev])
        test.extend(items[n_train + n_dev : n_train + n_dev + n_test])

    random.shuffle(train)
    random.shuffle(dev)
    random.shuffle(test)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT_DIR / "train.jsonl", train)
    write_jsonl(OUT_DIR / "dev.jsonl", dev)
    write_jsonl(OUT_DIR / "test.jsonl", test)

    print(
        f"train: {len(train)}  dev: {len(dev)}  test: {len(test)}  total: {len(rows)}"
    )

    # quick sanity distribution
    def dist(rs):
        c = Counter((r["use_case"], r["case_type"]) for r in rs)
        return c

    print("\nTop buckets in train:")
    for (uc, ct), v in dist(train).most_common(8):
        print(f"  {uc}/{ct}: {v}")

    print("\nTop buckets in dev:")
    for (uc, ct), v in dist(dev).most_common(8):
        print(f"  {uc}/{ct}: {v}")

    print("\nTop buckets in test:")
    for (uc, ct), v in dist(test).most_common(8):
        print(f"  {uc}/{ct}: {v}")


if __name__ == "__main__":
    main()
