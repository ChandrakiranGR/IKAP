#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.orchestration.retrieval_adapter import retrieve_kb_chunks


def load_cases(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected a JSON array in {path}")
    return [case for case in payload if isinstance(case, dict)]


def summarize_case(case: dict, results: list[dict]) -> dict:
    expected_kb_id = case["expected_kb_id"]
    returned_kb_ids = [item.get("kb_id", "") for item in results]
    top_result = results[0] if results else {}
    top_kb_id = top_result.get("kb_id", "")
    top_url = top_result.get("url", "")

    return {
        "id": case["id"],
        "category": case.get("category", ""),
        "question": case["question"],
        "expected_kb_id": expected_kb_id,
        "top_kb_id": top_kb_id,
        "top_title": top_result.get("title", ""),
        "top_url": top_url,
        "returned_kb_ids": returned_kb_ids,
        "top_1_match": top_kb_id == expected_kb_id,
        "hit_at_k": expected_kb_id in returned_kb_ids,
        "top_1_link_match": expected_kb_id in top_url,
    }


def print_case(result: dict) -> None:
    status = "PASS" if result["top_1_match"] else "FAIL"
    returned = ", ".join(result["returned_kb_ids"]) or "none"
    print(
        f"[{status}] {result['id']} | expected={result['expected_kb_id']} | "
        f"top={result['top_kb_id'] or 'none'} | returned={returned}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--cases",
        default="data/benchmarks/retrieval_benchmark.json",
        help="Benchmark case JSON file",
    )
    ap.add_argument(
        "--top_k",
        type=int,
        default=4,
        help="Number of KB results to request from the live retrieval path",
    )
    ap.add_argument(
        "--out",
        default="data/benchmarks/results/retrieval_benchmark_results.json",
        help="Optional JSON output path",
    )
    args = ap.parse_args()

    cases_path = Path(args.cases)
    cases = load_cases(cases_path)

    detailed_results = []
    for case in cases:
        results = retrieve_kb_chunks(case["question"], top_k=args.top_k)
        summary = summarize_case(case, results)
        detailed_results.append(summary)
        print_case(summary)

    total = len(detailed_results)
    top_1 = sum(1 for item in detailed_results if item["top_1_match"])
    hit_at_k = sum(1 for item in detailed_results if item["hit_at_k"])
    link_at_1 = sum(1 for item in detailed_results if item["top_1_link_match"])

    by_category = {}
    for category in sorted({item["category"] for item in detailed_results}):
        items = [item for item in detailed_results if item["category"] == category]
        by_category[category] = {
            "cases": len(items),
            "top_1_accuracy": round(
                sum(1 for item in items if item["top_1_match"]) / max(len(items), 1), 4
            ),
            "hit_at_k_accuracy": round(
                sum(1 for item in items if item["hit_at_k"]) / max(len(items), 1), 4
            ),
        }

    top_misses = Counter(
        item["top_kb_id"] for item in detailed_results if not item["top_1_match"]
    )

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases_file": str(cases_path),
        "top_k": args.top_k,
        "total_cases": total,
        "top_1_correct": top_1,
        "top_1_accuracy": round(top_1 / max(total, 1), 4),
        "hit_at_k_correct": hit_at_k,
        "hit_at_k_accuracy": round(hit_at_k / max(total, 1), 4),
        "top_1_link_correct": link_at_1,
        "top_1_link_accuracy": round(link_at_1 / max(total, 1), 4),
        "by_category": by_category,
        "most_common_wrong_top_kb_ids": top_misses.most_common(5),
        "results": detailed_results,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"Top-1 accuracy: {summary['top_1_correct']}/{total} = {summary['top_1_accuracy']:.1%}")
    print(f"Hit@{args.top_k}: {summary['hit_at_k_correct']}/{total} = {summary['hit_at_k_accuracy']:.1%}")
    print(
        f"Top-1 link accuracy: {summary['top_1_link_correct']}/{total} = "
        f"{summary['top_1_link_accuracy']:.1%}"
    )
    print(f"Wrote benchmark results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
