#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


ESCALATION_BLOCK = (
    "If this does not resolve your issue: Contact Northeastern IT Support and include:\n"
    "- Your device/OS\n"
    "- The step where the issue occurred\n"
    "- Any error message shown"
)
SEMICOLON_SECTION_SPLIT_RE = re.compile(r";\s+(?=[A-Z][A-Za-z0-9/&'() -]{1,80}:)")
NOTE_SPLIT_RE = re.compile(r"\bNote:\s+", re.I)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def clean_step_text(text: str) -> str:
    text = normalize_space(text)
    text = re.sub(r"\bto the to the\b", "to the", text, flags=re.I)
    text = re.sub(r"\bthe the\b", "the", text, flags=re.I)
    text = re.sub(r"\bto to\b", "to", text, flags=re.I)
    text = re.sub(r"\s+([:;,.])", r"\1", text)
    return text.strip()


def split_step_text(text: str) -> list[str]:
    text = clean_step_text(text)
    if not text:
        return []

    out: list[str] = []
    for part in SEMICOLON_SECTION_SPLIT_RE.split(text):
        part = clean_step_text(part)
        if not part:
            continue

        note_parts = NOTE_SPLIT_RE.split(part, maxsplit=1)
        main_step = clean_step_text(note_parts[0])
        if main_step:
            out.append(main_step)

        if len(note_parts) == 2:
            note_step = clean_step_text(note_parts[1])
            if note_step:
                if note_step.lower().startswith("if "):
                    out.append(note_step)
                else:
                    out.append(f"Note: {note_step}")

    return out


def sentence_chunks(text: str) -> list[str]:
    text = normalize_space(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return text or "kb"


def derive_category(doc: dict) -> str:
    joined = " | ".join(doc.get("categories") or [])
    lowered = joined.lower()
    title = (doc.get("title") or "").lower()

    if "multi-factor authentication" in lowered or "duo" in lowered or "mfa" in title:
        return "Multi-Factor Authentication (MFA)"
    if "vpn" in lowered or "globalprotect" in title or "vpn" in title:
        return "VPN access"
    if any(term in lowered for term in ["wireless", "nuwave", "eduroam"]) or any(
        term in title for term in ["nuwave", "eduroam", "wi-fi", "wireless"]
    ):
        return "WiFi and network connectivity"
    if "student hub" in lowered or "student hub" in title:
        return "Student Hub"
    if any(term in lowered for term in ["canvas", "turnitin", "qwickly", "respondus"]) or any(
        term in title for term in ["canvas", "turnitin", "qwickly", "respondus"]
    ):
        return "Canvas and teaching tools"
    if "software" in lowered or any(
        term in title for term in ["matlab", "tableau", "solidworks", "ansys", "mathematica", "abaqus"]
    ):
        return "Software access"
    if "account" in lowered or "password" in title:
        return "Account access"
    return "General IT support"


def build_steps(doc: dict, max_steps: int = 8) -> tuple[list[str], bool]:
    sections = doc.get("sections") or []

    ordered = []
    for section in sections:
        heading = normalize_space(section.get("heading", ""))
        steps: list[str] = []
        for raw_step in section.get("steps") or []:
            steps.extend(split_step_text(raw_step))
        text = normalize_space(section.get("text", ""))
        ordered.append({"heading": heading, "steps": steps, "text": text})

    step_sections = [item for item in ordered if item["steps"]]
    non_intro_step_sections = [
        item for item in step_sections if item["heading"].lower() not in {"introduction", "summary", "note", "help"}
    ]

    picked_sections = non_intro_step_sections or step_sections
    steps: list[str] = []
    seen: set[str] = set()

    for section in picked_sections:
        for step in section["steps"]:
            if not step:
                continue
            key = step.lower()
            if key in seen:
                continue
            seen.add(key)
            steps.append(step)
            if len(steps) >= max_steps:
                break
        if len(steps) >= max_steps:
            break

    if steps:
        return steps[:max_steps], True

    fallback_sentences: list[str] = []
    for section in ordered:
        if section["heading"]:
            fallback_sentences.append(f"{section['heading']}: {section['text']}".strip())
        elif section["text"]:
            fallback_sentences.append(section["text"])
    if not fallback_sentences:
        fallback_sentences = sentence_chunks(doc.get("plain_text", ""))

    out = []
    for sentence in fallback_sentences:
        out.extend(sentence_chunks(sentence))
        if len(out) >= max_steps:
            break

    return out[:max_steps], False


def draft_quality(doc: dict, steps: list[str], used_explicit_steps: bool) -> str:
    if not used_explicit_steps:
        return "low"

    if len(steps) >= 4:
        return "high"
    if len(steps) >= 2:
        return "medium"
    return "low"


def build_assistant_response(doc: dict, steps: list[str]) -> str:
    category = derive_category(doc)
    step_lines = [f"{idx}. {clean_step_text(step)}" for idx, step in enumerate(steps, start=1)]

    if not step_lines:
        step_lines = [
            "1. Review the referenced Northeastern KB article for the exact supported steps.",
            "2. Follow the instructions shown for your device or platform.",
            "3. If the process does not work as expected, contact Northeastern IT Support.",
        ]

    reference_url = doc.get("article_url") or doc.get("url") or "None"

    return (
        f"Category: {category}\n"
        f"Clarifying question: None\n"
        f"Steps:\n"
        + "\n".join(step_lines)
        + "\nReferences:\n"
        + (f"- {doc.get('title')}: {reference_url}" if reference_url and reference_url != "None" else "None")
        + "\n"
        + ESCALATION_BLOCK
    )


def build_user_question(doc: dict) -> str:
    title = normalize_space(doc.get("title", ""))
    if title.lower().startswith("faq:"):
        topic = title.split(":", 1)[1].strip().rstrip("?")
        return f"What should I know about {topic}?"
    if title.endswith("?"):
        return title
    return f"{title}?"


def load_holdout_ids(paths: list[Path]) -> set[str]:
    holdout = set()
    for path in paths:
        if not path.exists():
            continue
        payload = load_json(path)
        if isinstance(payload, list):
            for item in payload:
                kb_id = (item or {}).get("expected_kb_id")
                if kb_id:
                    holdout.add(kb_id)
    return holdout


def split_name(article_id: str, holdout_ids: set[str]) -> str:
    if article_id in holdout_ids:
        return "holdout"

    bucket = int(hashlib.sha256(article_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket == 0:
        return "dev"
    return "train"


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
    ap.add_argument("--kb_dir", default="data/processed/kb_json")
    ap.add_argument("--out_dir", default="data/dataset")
    ap.add_argument(
        "--holdout_cases",
        nargs="*",
        default=[
            "data/benchmarks/answer_eval_cases.json",
            "data/benchmarks/answer_eval_cases_extended.json",
            "data/benchmarks/retrieval_benchmark.json",
        ],
    )
    ap.add_argument(
        "--include_low_confidence",
        action="store_true",
        help="Include low-confidence drafts that do not have strong procedural steps",
    )
    args = ap.parse_args()

    kb_dir = Path(args.kb_dir)
    out_dir = Path(args.out_dir)
    holdout_ids = load_holdout_ids([Path(p) for p in args.holdout_cases])

    train_rows = []
    dev_rows = []
    holdout_rows = []
    review_rows = []

    for fp in sorted(kb_dir.glob("*.json")):
        doc = load_json(fp)
        article_id = doc.get("article_id") or fp.stem
        steps, used_explicit_steps = build_steps(doc)
        quality = draft_quality(doc, steps, used_explicit_steps)
        if quality == "low" and not args.include_low_confidence:
            continue

        user_question = build_user_question(doc)
        assistant_response = build_assistant_response(doc, steps)
        split = split_name(article_id, holdout_ids)

        example = {
            "id": slugify(f"{article_id}-{user_question}")[:80],
            "article_id": article_id,
            "title": doc.get("title", ""),
            "split": split,
            "draft_quality": quality,
            "messages": [
                {"role": "user", "content": user_question},
                {"role": "assistant", "content": assistant_response},
            ],
        }

        review_rows.append(
            {
                "article_id": article_id,
                "title": doc.get("title", ""),
                "split": split,
                "draft_quality": quality,
                "source_export": doc.get("source_export", ""),
                "question": user_question,
                "reference_url": doc.get("article_url") or doc.get("url") or "",
                "review_status": "todo",
                "notes": "",
            }
        )

        if split == "holdout":
            holdout_rows.append(example)
        elif split == "dev":
            dev_rows.append(example)
        else:
            train_rows.append(example)

    write_jsonl(out_dir / "draft_train.jsonl", train_rows)
    write_jsonl(out_dir / "draft_dev.jsonl", dev_rows)
    write_jsonl(out_dir / "draft_holdout.jsonl", holdout_rows)
    write_csv(out_dir / "draft_review_queue.csv", review_rows)

    print(f"Holdout KB IDs reserved from benchmarks: {len(holdout_ids)}")
    print(f"Train examples: {len(train_rows)}")
    print(f"Dev examples: {len(dev_rows)}")
    print(f"Holdout examples: {len(holdout_rows)}")
    print(f"Review queue: {len(review_rows)} rows -> {out_dir / 'draft_review_queue.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
