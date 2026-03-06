#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from collections import Counter

DATASET = Path("data/dataset/all.jsonl")

CASE_TYPES = {"typical", "edge", "adversarial"}
URL_RE = re.compile(
    r"https?://\S+|www\.\S+|[A-Za-z0-9.-]+\.[A-Za-z]{2,}/\S+", re.IGNORECASE
)


def main():
    if not DATASET.exists():
        print(f"[FAIL] Missing {DATASET}")
        sys.exit(1)

    total = 0
    bad = 0
    ids = set()
    dup_ids = 0

    use_case_counts = Counter()
    case_type_counts = Counter()
    bucket_counts = Counter()

    with DATASET.open("r", encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            total += 1

            try:
                rec = json.loads(line)
            except Exception:
                bad += 1
                print(f"[L{ln}] invalid JSON")
                continue

            # required top-level fields
            for k in [
                "id",
                "use_case",
                "case_type",
                "user_query",
                "expected_output",
                "guardrails",
                "source",
            ]:
                if k not in rec:
                    bad += 1
                    print(f"[L{ln}] missing field: {k}")
                    continue

            rid = rec.get("id")
            if rid in ids:
                dup_ids += 1
            ids.add(rid)

            uc = rec.get("use_case", "")
            ct = rec.get("case_type", "")
            use_case_counts[uc] += 1
            case_type_counts[ct] += 1
            bucket_counts[(uc, ct)] += 1

            if ct not in CASE_TYPES:
                bad += 1
                print(f"[L{ln}] invalid case_type: {ct} (id={rid})")

            eo = rec.get("expected_output", {})
            if not isinstance(eo, dict):
                bad += 1
                print(f"[L{ln}] expected_output not a dict (id={rid})")
                continue

            for k in ["category", "steps", "escalation"]:
                if k not in eo:
                    bad += 1
                    print(f"[L{ln}] expected_output missing {k} (id={rid})")

            steps = eo.get("steps", [])
            if not isinstance(steps, list) or len(steps) < 2:
                bad += 1
                print(f"[L{ln}] steps must be list with >=2 items (id={rid})")

            # keep expected_output free of raw URLs (use [REDACTED_URL] or [URL])
            joined = (
                " ".join([str(x) for x in steps]) + " " + str(eo.get("escalation", ""))
            )
            if URL_RE.search(joined):
                bad += 1
                print(f"[L{ln}] URL found in expected_output (id={rid})")

    print(f"Total rows: {total}")
    print(f"Invalid rows: {bad}")
    print(f"Duplicate ids: {dup_ids}")

    print("\nCounts by use_case:")
    for k, v in use_case_counts.most_common():
        print(f"  {k}: {v}")

    print("\nCounts by case_type:")
    for k, v in case_type_counts.most_common():
        print(f"  {k}: {v}")

    if bad == 0 and dup_ids == 0:
        print("\n[OK] Dataset validation passed.")
        sys.exit(0)
    else:
        print("\n[FAIL] Fix the issues above and re-run validation.")
        sys.exit(1)


if __name__ == "__main__":
    main()
