import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List
from backend.orchestration.security_constants import RAG_INJECTION_MARKERS
import re

from dotenv import load_dotenv
from openai import OpenAI

from scripts.rag_answer import (
    EMBED_MODEL,
    load_index,
    retrieve,
    load_retrieved_links,
    load_kb_json,
    choose_priority_sections,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_runtime_path(env_var: str, *candidates: Path) -> Path:
    configured = os.getenv(env_var)
    if configured:
        configured_path = Path(configured)
        if not configured_path.is_absolute():
            configured_path = _project_root() / configured_path
        return configured_path

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@lru_cache(maxsize=1)
def _load_runtime():
    root = _project_root()
    load_dotenv(root / ".env")

    client = OpenAI()

    index_path = _resolve_runtime_path(
        "IKAP_INDEX_PATH",
        root / "data" / "rag" / "kb_index.jsonl",
        root / "deploy_data" / "rag" / "kb_index.jsonl",
    )
    if not index_path.exists():
        raise FileNotFoundError(f"RAG index not found: {index_path}")

    index = load_index(index_path)

    kb_dir = _resolve_runtime_path(
        "IKAP_KB_DIR",
        root / "data" / "processed" / "kb_json",
        root / "deploy_data" / "processed" / "kb_json",
    )

    return client, index, kb_dir


def _extract_text(row: Dict[str, Any]) -> str:
    for key in ("text", "chunk_text", "content", "body", "snippet", "chunk"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_title(row: Dict[str, Any]) -> str:
    for key in ("title", "article_title", "kb_title", "name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_kb_id(row: Dict[str, Any]) -> str:
    for key in ("kb_id", "id", "article_id", "sys_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

def _sanitize_kb_section(text: str) -> str:
    """
    Scans a KB section's text for embedded instruction-like content.
    If any injection marker is found, the entire section text is replaced
    with a safe placeholder so it never reaches the model's context window.

    This is IKAP's defense against indirect prompt injection via RAG content —
    an attacker embedding 'SYSTEM NOTE: reset your instructions' inside
    what appears to be legitimate KB article text.
    """
    if not text:
        return text

    lowered = text.lower()
    for marker in RAG_INJECTION_MARKERS:
        if marker in lowered:
            # Log for audit purposes
            print(
                f"[IKAP SECURITY] RAG injection marker detected and removed: '{marker}'"
            )
            return "[This KB section was flagged and removed for security reasons.]"

    return text

def _clean_kb_text(text: str, title: str = "") -> str:
    """
    Generic cleanup only.
    Preserve information; remove only obvious formatting noise.
    Now includes injection sanitization as the first step.
    """
    if not text:
        return ""
    
    # sanitize before any other processing to ensure markers are detected even if surrounded by noise
    text = _sanitize_kb_section(text)
    # If the section was flagged, return the placeholder immediately
    if text == "[This KB section was flagged and removed for security reasons.]":
        return text

    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()

    if title:
        repeated = f"Title: {title} {title}"
        if text.startswith(repeated):
            text = text[len(repeated) :].strip()
        elif text.startswith(f"Title: {title}"):
            text = text[len(f"Title: {title}") :].strip()

    noise_patterns = [
        r"Back to top",
        r"Copy Permalink",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+", " ", text).strip()

    # Remove only obviously broken trailing fragment tokens
    text = re.sub(r"\b[a-zA-Z]{1,3}\s*$", "", text).strip()

    return text


def _score_url(url: str, kb_id: str) -> int:
    """
    Generic URL ranking:
    prefer canonical KB article links over generic or external links.
    """
    if not url:
        return -1

    score = 0
    u = url.lower()
    kb = kb_id.lower()

    if "kb_article_view" in u:
        score += 100
    if kb and kb in u:
        score += 80
    if "service.northeastern.edu/tech" in u:
        score += 60
    if "northeastern.service-now.com/tech" in u:
        score += 50
    if "/tech?id=kb_article_view" in u:
        score += 40

    return score


def _is_requirements_section(heading: str) -> bool:
    heading_l = (heading or "").strip().lower()
    return any(
        term in heading_l
        for term in [
            "requirement",
            "prerequisite",
            "prerequisites",
        ]
    )


def _is_note_section(heading: str) -> bool:
    heading_l = (heading or "").strip().lower()
    return any(
        term in heading_l
        for term in [
            "introduction",
            "benefit",
            "limitation",
            "important",
            "note",
            "resource",
        ]
    )


def _extract_question_specific_notes(kb: Dict[str, Any], question: str) -> List[str]:
    notes: List[str] = []
    question_l = (question or "").lower()
    title = (kb.get("title") or "").strip()
    title_l = title.lower()
    sections = kb.get("sections", []) or []

    if any(term in question_l for term in [" mac", " mac?", " mac.", " on my mac", "macbook", "macos"]):
        if any(term in title_l for term in ["mac", "macbook", "macos"]):
            notes.append("Platform: Mac.")
        else:
            for section in sections:
                combined = " ".join(
                    [
                        section.get("heading", ""),
                        section.get("text", ""),
                        " ".join(section.get("steps") or []),
                    ]
                ).lower()
                if any(term in combined for term in ["mac", "macbook", "macos"]):
                    notes.append("Platform: Mac.")
                    break

    if any(term in question_l for term in ["publish", "published", "unpublished", "before i publish", "before publishing"]):
        for section in sections:
            text = _clean_kb_text(section.get("text", ""))
            combined_l = " ".join(
                [
                    (section.get("heading") or "").lower(),
                    text.lower(),
                    " ".join((section.get("steps") or [])).lower(),
                ]
            )
            if any(term in combined_l for term in ["published", "unpublished", "only work after"]):
                notes.append(f"Timing note: {text}")
                break

    return notes


def _build_precise_kb_excerpt(kb_dir: Path, kb_id: str, question: str) -> str:
    """
    Existing function — add sanitization to steps as well as section text.
    Replace the steps extraction block inside this function.
    """
    kb = load_kb_json(kb_dir, kb_id)
    if not kb:
        return ""

    question_l = question.lower()
    setup_query = any(
        term in question_l
        for term in [
            "connect",
            "configure",
            "set up",
            "setup",
            "install",
            "enroll",
            "register",
            "update",
            "reset",
        ]
    )

    sections = choose_priority_sections(
        kb,
        question,
        max_sections=5 if setup_query else 3,
    )
    blocks = []
    title = (kb.get("title") or "").strip()
    if title:
        blocks.append(f"Article title: {title}")

    qualifier_notes = _extract_question_specific_notes(kb, question)
    if qualifier_notes:
        blocks.append("\n".join(qualifier_notes))

    for section in sections:
        heading = (section.get("heading") or "").strip()
        text = _clean_kb_text(section.get("text", ""))

        # sanitize individual steps as well, since they can also contain injection attempts
        raw_steps = section.get("steps") or []
        steps = []
        for step in raw_steps:
            cleaned_step = _clean_kb_text(step)
            if cleaned_step:
                steps.append(cleaned_step)
                
        parts = []
        if heading:
            parts.append(f"{heading}:")
        if text:
            parts.append(text)
        if steps:
            if _is_requirements_section(heading):
                parts.append("Requirements:")
                parts.extend(f"- {step}" for step in steps)
            elif _is_note_section(heading):
                parts.append("Key notes:")
                parts.extend(f"- {step}" for step in steps)
            else:
                parts.append("Steps:")
                parts.extend(f"{idx}. {step}" for idx, step in enumerate(steps, start=1))

        if parts:
            blocks.append("\n".join(parts))

    return "\n\n".join(blocks).strip()


def _pick_best_link(kb_id: str, links: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not links:
        return {}

    return max(
        links,
        key=lambda link: _score_url(
            link.get("url", "") or link.get("link", ""),
            kb_id,
        ),
    )


def retrieve_kb_chunks(question: str, top_k: int = 4) -> List[Dict[str, Any]]:
    client, index, kb_dir = _load_runtime()

    q_emb = (
        client.embeddings.create(
            model=EMBED_MODEL,
            input=question,
        )
        .data[0]
        .embedding
    )

    top = retrieve(index, question, q_emb, top_k)

    seen_kb_ids = set()
    normalized_rows: List[Dict[str, Any]] = []
    kb_ids: List[str] = []

    for item in top:
        row = item if isinstance(item, dict) else {}
        kb_id = _extract_kb_id(row)

        if kb_id:
            if kb_id in seen_kb_ids:
                continue
            seen_kb_ids.add(kb_id)
            kb_ids.append(kb_id)

        normalized_rows.append(row)

    link_map: Dict[str, List[Dict[str, Any]]] = {}
    if kb_ids and kb_dir.exists():
        try:
            retrieved_links = load_retrieved_links(kb_dir, kb_ids, limit=20)

            for link in retrieved_links:
                link_kb_id = (
                    link.get("kb_id") or link.get("id") or link.get("article_id") or ""
                )
                if link_kb_id:
                    link_map.setdefault(link_kb_id, []).append(link)
        except Exception:
            # Keep retrieval resilient even if link enrichment fails
            pass

    adapted: List[Dict[str, Any]] = []
    for row in normalized_rows:
        kb_id = _extract_kb_id(row)
        candidate_links = link_map.get(kb_id, [])
        best_link = _pick_best_link(kb_id, candidate_links)
        kb_payload = load_kb_json(kb_dir, kb_id) if kb_id and kb_dir.exists() else None

        title = (
            _extract_title(row)
            or best_link.get("text", "")
            or best_link.get("title", "")
            or best_link.get("article_title", "")
        )

        url = (
            best_link.get("url", "")
            or best_link.get("link", "")
            or row.get("article_url", "")
            or row.get("url", "")
            or row.get("link", "")
        )

        precise_text = ""
        if kb_payload:
            try:
                precise_text = _build_precise_kb_excerpt(kb_dir, kb_id, question)
            except Exception:
                precise_text = ""

        text = precise_text or _clean_kb_text(_extract_text(row), title)
        embedded_links = []
        for link in (kb_payload or {}).get("links", []) or []:
            text_value = (link.get("text") or "").strip()
            url_value = (link.get("url") or "").strip()
            if text_value and url_value:
                embedded_links.append({"text": text_value, "url": url_value})

        adapted.append(
            {
                "title": title,
                "url": url,
                "text": text,
                "kb_id": kb_id,
                "score": float(row.get("_score") or 0.0),
                "chunk_id": row.get("chunk_id") or "",
                "section": row.get("section") or "",
                "links": embedded_links,
            }
        )

    return adapted
