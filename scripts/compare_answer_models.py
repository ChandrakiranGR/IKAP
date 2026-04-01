#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_FINAL_MODEL = "gpt-4o-mini"
LATEST_FINETUNED_MODEL = (
    "ft:gpt-4o-mini-2024-07-18:northeastern-university:ikap-kb-assistant:DPxWpYzh"
)


def load_cases(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected a JSON array in {path}")
    return [case for case in payload if isinstance(case, dict)]


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return cleaned or "model"


def parse_model_arg(value: str) -> dict:
    if "=" in value:
        label, model = value.split("=", 1)
        return {"label": label.strip(), "model": model.strip(), "source": "cli"}
    return {"label": value.strip(), "model": value.strip(), "source": "cli"}


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_job_status(job_id: str) -> dict:
    if not job_id:
        return {}
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    job = client.fine_tuning.jobs.retrieve(job_id)
    return {
        "status": (getattr(job, "status", "") or "").strip(),
        "model": (getattr(job, "fine_tuned_model", "") or "").strip(),
    }


def resolve_manifest_candidate(path: Path) -> dict:
    payload = load_manifest(path)
    job = payload.get("job") or {}
    job_id = payload.get("fine_tuning_job_id") or job.get("id") or ""
    status = (payload.get("status") or job.get("status") or "").strip()
    model = (
        payload.get("fine_tuned_model")
        or job.get("fine_tuned_model")
        or ""
    ).strip()
    if not model and job_id:
        live = refresh_job_status(job_id)
        status = live.get("status") or status
        model = live.get("model") or model
    label = (
        payload.get("suffix")
        or job.get("user_provided_suffix")
        or path.stem
    ).strip()
    return {
        "label": label,
        "model": model,
        "status": status,
        "job_id": job_id,
        "manifest": str(path),
        "source": "manifest",
    }


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for candidate in candidates:
        key = (candidate.get("label", ""), candidate.get("model", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def evaluate_model(
    *,
    label: str,
    model_name: str,
    cases: list[dict],
    top_k: int,
    cases_file: Path,
) -> dict:
    from backend.orchestration.langchain_pipeline import IKAPLangChainPipeline
    from backend.orchestration.retrieval_adapter import retrieve_kb_chunks
    from scripts.run_answer_eval import score_case, summarize

    pipeline = IKAPLangChainPipeline(model_name=model_name, top_k=top_k)
    results = []

    for case in cases:
        retrieved = retrieve_kb_chunks(case["question"], top_k=top_k)
        response = pipeline.invoke(case["question"])
        results.append(score_case(case, response, retrieved))

    summary = summarize(results)
    return {
        "label": label,
        "model": pipeline.model_name,
        "cases_file": str(cases_file),
        "top_k": top_k,
        "summary": summary,
        "results": results,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_best(results: list[dict]) -> dict | None:
    if not results:
        return None
    ordered = sorted(
        results,
        key=lambda item: (
            item["summary"]["pass_rate"],
            item["summary"]["expected_reference_ok_rate"],
            item["summary"]["required_terms_ok_rate"],
            item["summary"]["unsafe_refusal_ok_rate"],
        ),
        reverse=True,
    )
    best = ordered[0]
    return {
        "label": best["label"],
        "model": best["model"],
        "pass_rate": best["summary"]["pass_rate"],
        "passed_cases": best["summary"]["passed_cases"],
        "total_cases": best["summary"]["total_cases"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--cases",
        default="data/benchmarks/answer_eval_cases_extended.json",
        help="Answer evaluation case JSON file",
    )
    ap.add_argument("--top_k", type=int, default=4)
    ap.add_argument(
        "--out",
        default="data/benchmarks/results/model_comparison.json",
        help="Comparison summary JSON output path",
    )
    ap.add_argument(
        "--details_dir",
        default="data/benchmarks/results/model_comparison",
        help="Directory for per-model detailed result files",
    )
    ap.add_argument(
        "--model",
        action="append",
        default=[],
        help="Candidate model in MODEL or LABEL=MODEL format. Repeatable.",
    )
    ap.add_argument(
        "--manifest",
        action="append",
        default=[],
        help="Optional fine-tune job manifest to resolve and include if finished. Repeatable.",
    )
    ap.add_argument(
        "--skip-defaults",
        action="store_true",
        help="Do not include the default base and FT-v1 candidates automatically.",
    )
    ap.add_argument(
        "--list-only",
        action="store_true",
        help="Resolve candidate models and manifests without running evaluations.",
    )
    args = ap.parse_args()

    cases_file = PROJECT_ROOT / args.cases
    details_dir = PROJECT_ROOT / args.details_dir
    cases = load_cases(cases_file)

    candidates = []
    if not args.skip_defaults:
        candidates.extend(
            [
                {"label": "base", "model": DEFAULT_FINAL_MODEL, "source": "default"},
                {
                    "label": "ft_v1",
                    "model": LATEST_FINETUNED_MODEL,
                    "source": "default",
                },
            ]
        )

    for value in args.model:
        parsed = parse_model_arg(value)
        if parsed["model"]:
            candidates.append(parsed)

    pending = []
    for manifest_arg in args.manifest:
        manifest_path = PROJECT_ROOT / manifest_arg
        candidate = resolve_manifest_candidate(manifest_path)
        if candidate["model"]:
            candidates.append(candidate)
        else:
            pending.append(candidate)

    candidates = dedupe_candidates(candidates)

    if args.list_only:
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "cases_file": str(cases_file),
            "top_k": args.top_k,
            "ready_candidates": candidates,
            "pending_candidates": pending,
        }
        write_json(PROJECT_ROOT / args.out, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"Wrote candidate summary to {PROJECT_ROOT / args.out}")
        return 0

    comparison_results = []
    for candidate in candidates:
        print(f"Evaluating {candidate['label']} -> {candidate['model']}")
        payload = evaluate_model(
            label=candidate["label"],
            model_name=candidate["model"],
            cases=cases,
            top_k=args.top_k,
            cases_file=cases_file,
        )
        comparison_results.append(payload)

        detail_path = details_dir / f"{slugify(candidate['label'])}.json"
        write_json(detail_path, payload)
        summary = payload["summary"]
        print(
            f"  pass={summary['passed_cases']}/{summary['total_cases']} "
            f"({summary['pass_rate']:.1%})"
        )

    comparison_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases_file": str(cases_file),
        "top_k": args.top_k,
        "winner": select_best(comparison_results),
        "pending_candidates": pending,
        "models": [
            {
                "label": payload["label"],
                "model": payload["model"],
                "summary": payload["summary"],
                "details_file": str(details_dir / f"{slugify(payload['label'])}.json"),
            }
            for payload in comparison_results
        ],
    }

    write_json(PROJECT_ROOT / args.out, comparison_payload)
    print(f"Wrote comparison summary to {PROJECT_ROOT / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
