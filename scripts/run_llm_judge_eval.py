#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.orchestration.langchain_pipeline import IKAPLangChainPipeline
from backend.orchestration.retrieval_adapter import retrieve_kb_chunks


JUDGE_PROMPT_PATH = (
    PROJECT_ROOT / "prompt_engineering" / "prompts" / "llm_judge_system_prompt.txt"
)
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def load_cases(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected a JSON array in {path}")
    return [case for case in payload if isinstance(case, dict)]


def load_judge_prompt() -> str:
    if not JUDGE_PROMPT_PATH.exists():
        raise FileNotFoundError(f"Judge prompt not found: {JUDGE_PROMPT_PATH}")
    return JUDGE_PROMPT_PATH.read_text(encoding="utf-8").strip()


def compact_sources(chunks: list[dict]) -> list[dict]:
    compacted = []
    for chunk in chunks:
        compacted.append(
            {
                "kb_id": chunk.get("kb_id", ""),
                "title": chunk.get("title", ""),
                "url": chunk.get("url", ""),
                "section": chunk.get("section", ""),
                "text": (chunk.get("text", "") or "")[:1200],
            }
        )
    return compacted


def build_case_payload(case: dict, answer: str, retrieved: list[dict]) -> dict:
    return {
        "case": {
            "id": case.get("id", ""),
            "category": case.get("category", ""),
            "case_type": case.get("case_type", ""),
            "question": case.get("question", ""),
            "expected_kb_id": case.get("expected_kb_id", ""),
            "expected_reference_url": case.get("expected_reference_url", ""),
            "required_terms": case.get("required_terms", []),
            "forbidden_terms": case.get("forbidden_terms", []),
            "min_steps": case.get("min_steps", 0),
        },
        "retrieved_sources": compact_sources(retrieved),
        "assistant_answer": answer,
    }


def extract_json_block(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = JSON_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))


def judge_case(
    *,
    client: OpenAI,
    judge_model: str,
    system_prompt: str,
    case_payload: dict,
    timeout: float,
) -> dict:
    response = client.chat.completions.create(
        model=judge_model,
        temperature=0,
        timeout=timeout,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(case_payload, ensure_ascii=False, indent=2),
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    judged = extract_json_block(content)
    judged.setdefault("overall_score", 0)
    judged.setdefault("pass", False)
    judged.setdefault("scores", {})
    judged.setdefault("strengths", [])
    judged.setdefault("issues", [])
    judged.setdefault("summary", "")
    return judged


def summarize(results: list[dict]) -> dict:
    if not results:
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_cases": 0,
            "passed_cases": 0,
            "pass_rate": 0.0,
            "average_overall_score": 0.0,
            "average_scores": {},
            "by_category": {},
        }

    dimensions = [
        "relevance",
        "groundedness",
        "completeness",
        "clarity",
        "tone",
        "reference_quality",
    ]

    average_scores = {
        dimension: round(
            mean(float(item["judge"]["scores"].get(dimension, 0)) for item in results), 3
        )
        for dimension in dimensions
    }

    by_category = {}
    categories = sorted({item["category"] for item in results})
    for category in categories:
        items = [item for item in results if item["category"] == category]
        by_category[category] = {
            "cases": len(items),
            "pass_rate": round(
                sum(1 for item in items if item["judge"]["pass"]) / max(len(items), 1),
                4,
            ),
            "average_overall_score": round(
                mean(float(item["judge"]["overall_score"]) for item in items),
                3,
            ),
        }

    passed_cases = sum(1 for item in results if item["judge"]["pass"])
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(results),
        "passed_cases": passed_cases,
        "pass_rate": round(passed_cases / max(len(results), 1), 4),
        "average_overall_score": round(
            mean(float(item["judge"]["overall_score"]) for item in results), 3
        ),
        "average_scores": average_scores,
        "by_category": by_category,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--cases",
        default="data/benchmarks/answer_eval_cases_extended.json",
        help="Evaluation cases JSON file",
    )
    ap.add_argument("--top_k", type=int, default=4)
    ap.add_argument(
        "--model",
        default="",
        help="Optional answer model override",
    )
    ap.add_argument(
        "--judge-model",
        default="gpt-4o-mini",
        help="LLM judge model",
    )
    ap.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Optional limit for smoke tests",
    )
    ap.add_argument(
        "--out",
        default="data/benchmarks/results/llm_judge_eval_results.json",
        help="Output JSON path",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-API-call timeout in seconds",
    )
    args = ap.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    cases = load_cases(PROJECT_ROOT / args.cases)
    if args.max_cases > 0:
        cases = cases[: args.max_cases]

    pipeline = IKAPLangChainPipeline(model_name=args.model or None, top_k=args.top_k)
    judge_prompt = load_judge_prompt()

    results = []
    for case in cases:
        print(f"Running case: {case.get('id', '')}", flush=True)
        retrieved = retrieve_kb_chunks(case["question"], top_k=args.top_k)
        answer = pipeline.invoke(case["question"])
        case_payload = build_case_payload(case, answer, retrieved)
        judged = judge_case(
            client=client,
            judge_model=args.judge_model,
            system_prompt=judge_prompt,
            case_payload=case_payload,
            timeout=args.timeout,
        )
        result = {
            "id": case.get("id", ""),
            "category": case.get("category", ""),
            "case_type": case.get("case_type", ""),
            "question": case.get("question", ""),
            "answer_model": pipeline.model_name,
            "judge_model": args.judge_model,
            "answer": answer,
            "retrieved_kb_ids": [item.get("kb_id", "") for item in retrieved],
            "judge": judged,
        }
        results.append(result)
        print(
            f"[{'PASS' if judged.get('pass') else 'FAIL'}] {case.get('id', '')} | "
            f"overall={judged.get('overall_score')} | "
            f"relevance={judged.get('scores', {}).get('relevance', 0)} | "
            f"groundedness={judged.get('scores', {}).get('groundedness', 0)}",
            flush=True,
        )

        partial_payload = {
            "cases_file": str(PROJECT_ROOT / args.cases),
            "answer_model": pipeline.model_name,
            "judge_model": args.judge_model,
            "top_k": args.top_k,
            "summary": summarize(results),
            "results": results,
        }
        out_path = PROJECT_ROOT / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(partial_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    summary = summarize(results)
    payload = {
        "cases_file": str(PROJECT_ROOT / args.cases),
        "answer_model": pipeline.model_name,
        "judge_model": args.judge_model,
        "top_k": args.top_k,
        "summary": summary,
        "results": results,
    }

    out_path = PROJECT_ROOT / args.out
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print(
        f"LLM-judge pass rate: {summary['passed_cases']}/{summary['total_cases']} = "
        f"{summary['pass_rate']:.1%}"
    )
    print(f"Average overall score: {summary['average_overall_score']:.2f}/5")
    print(f"Wrote LLM-judge eval results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
