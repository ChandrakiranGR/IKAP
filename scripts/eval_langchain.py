import argparse
import json
import jsonlines
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.orchestration.langchain_pipeline import IKAPLangChainPipeline  # noqa: E402


URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")


def load_examples(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() == ".jsonl":
        with jsonlines.open(path) as reader:
            return [row for row in reader]

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("examples", "records", "data", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        raise ValueError(f"Unsupported JSON structure in {path}")

    raise ValueError(f"Unsupported file type: {path.suffix}")


def extract_question(example: Dict[str, Any]) -> str:
    direct_keys = ("question", "query", "user_query", "input", "prompt")
    for key in direct_keys:
        value = example.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    messages = example.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

    raise ValueError(f"Could not extract question from example: {example}")


def extract_expected_category(example: Dict[str, Any]) -> Optional[str]:
    for key in ("expected_category", "category", "label", "intent"):
        value = example.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _collect_urls(value: Any) -> List[str]:
    urls: List[str] = []

    if isinstance(value, str):
        urls.extend(URL_PATTERN.findall(value))
    elif isinstance(value, list):
        for item in value:
            urls.extend(_collect_urls(item))
    elif isinstance(value, dict):
        for key in ("url", "link", "href"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                urls.append(v.strip())
        for nested in value.values():
            urls.extend(_collect_urls(nested))

    return urls


def extract_expected_urls(example: Dict[str, Any]) -> List[str]:
    urls: List[str] = []

    for key in (
        "expected_urls",
        "grounded_urls",
        "kb_urls",
        "references",
        "urls",
        "source_urls",
    ):
        if key in example:
            urls.extend(_collect_urls(example[key]))

    # dedupe while preserving order
    deduped: List[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)

    return deduped


def parse_section_lines(text: str, section_name: str) -> List[str]:
    lines = text.splitlines()
    collecting = False
    collected: List[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped.lower() == f"{section_name.lower()}:":
            collecting = True
            continue

        if collecting and re.match(r"^[A-Za-z][A-Za-z /()-]*:\s*$", stripped):
            break

        if collecting:
            collected.append(line)

    return collected


def extract_category(response: str) -> Optional[str]:
    m = re.search(r"^Category:\s*(.+)$", response, flags=re.MULTILINE)
    return m.group(1).strip() if m else None


def count_steps(response: str) -> int:
    step_lines = parse_section_lines(response, "Steps")
    count = 0
    for line in step_lines:
        if re.match(r"^\s*\d+\.\s+", line):
            count += 1
    return count


def extract_output_urls(response: str) -> List[str]:
    urls = URL_PATTERN.findall(response)
    deduped: List[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}?{parsed.query}".rstrip(
            "?"
        )
    except Exception:
        return url.strip().lower()


def format_ok(response: str) -> bool:
    required = ["Category:", "Clarifying question:", "Steps:", "References:"]
    return all(marker in response for marker in required)


def grounded_url_ok(output_urls: List[str], expected_urls: List[str]) -> Optional[bool]:
    if not expected_urls:
        return None

    if not output_urls:
        return True

    expected_norm = {normalize_url(url) for url in expected_urls}
    for out in output_urls:
        if normalize_url(out) not in expected_norm:
            return False
    return True


def evaluate_examples(
    examples: List[Dict[str, Any]],
    top_k: int,
) -> Dict[str, Any]:
    pipeline = IKAPLangChainPipeline(top_k=top_k)

    results: List[Dict[str, Any]] = []

    for idx, example in enumerate(examples, start=1):
        question = extract_question(example)
        expected_category = extract_expected_category(example)
        expected_urls = extract_expected_urls(example)

        response = pipeline.invoke(question)

        actual_category = extract_category(response)
        output_urls = extract_output_urls(response)

        row = {
            "index": idx,
            "question": question,
            "response": response,
            "expected_category": expected_category,
            "actual_category": actual_category,
            "category_match": (
                None
                if expected_category is None
                else actual_category == expected_category
            ),
            "expected_urls": expected_urls,
            "output_urls": output_urls,
            "grounded_url_ok": grounded_url_ok(output_urls, expected_urls),
            "format_ok": format_ok(response),
            "step_count": count_steps(response),
            "response_nonempty": bool(response.strip()),
        }
        results.append(row)

    summary = build_summary(results, top_k=top_k)
    return {"summary": summary, "results": results}


def mean(values: List[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def rate(values: List[bool]) -> float:
    return round(sum(1 for v in values if v) / len(values), 4) if values else 0.0


def build_summary(results: List[Dict[str, Any]], top_k: int) -> Dict[str, Any]:
    format_values = [r["format_ok"] for r in results]
    nonempty_values = [r["response_nonempty"] for r in results]
    step_values = [r["step_count"] for r in results]

    category_values = [
        r["category_match"] for r in results if r["category_match"] is not None
    ]
    grounded_values = [
        r["grounded_url_ok"] for r in results if r["grounded_url_ok"] is not None
    ]

    return {
        "num_examples": len(results),
        "top_k": top_k,
        "avg_steps": mean(step_values),
        "format_ok_rate": rate(format_values),
        "response_nonempty_rate": rate(nonempty_values),
        "category_accuracy": None if not category_values else rate(category_values),
        "grounded_url_rate": None if not grounded_values else rate(grounded_values),
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with jsonlines.open(path, mode="w") as writer:
        writer.write_all(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", required=True, help="Path to JSON or JSONL evaluation set"
    )
    parser.add_argument(
        "--summary_out", default="data/evals/langchain_eval_summary.json"
    )
    parser.add_argument(
        "--details_out", default="data/evals/langchain_eval_details.jsonl"
    )
    parser.add_argument("--top_k", type=int, default=1)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    input_path = (
        (PROJECT_ROOT / args.input).resolve()
        if not Path(args.input).is_absolute()
        else Path(args.input)
    )
    summary_out = (
        (PROJECT_ROOT / args.summary_out).resolve()
        if not Path(args.summary_out).is_absolute()
        else Path(args.summary_out)
    )
    details_out = (
        (PROJECT_ROOT / args.details_out).resolve()
        if not Path(args.details_out).is_absolute()
        else Path(args.details_out)
    )

    examples = load_examples(input_path)
    evaluation = evaluate_examples(examples, top_k=args.top_k)

    write_json(summary_out, evaluation["summary"])
    write_jsonl(details_out, evaluation["results"])

    print("\nEvaluation complete.")
    print(json.dumps(evaluation["summary"], indent=2))


if __name__ == "__main__":
    main()
