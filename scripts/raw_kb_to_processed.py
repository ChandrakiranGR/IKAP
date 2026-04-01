#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urldefrag, urlparse


NOISE_SECTION_HEADINGS = {
    "table of contents",
    "table of contents:",
    "table of contents .",
    "table of contents:",
    "contents",
    "related articles",
}

NOISE_SECTION_PLACEHOLDERS = {
    "heading",
    "section",
    "text",
    "steps",
}

NOISE_LINK_TEXT = {
    "back to top",
    "copy permalink",
}

GENERIC_SERVICE_URLS = {
    "https://service.northeastern.edu/tech",
    "https://service.northeastern.edu/tech/",
    "https://northeastern.service-now.com/tech",
    "https://northeastern.service-now.com/tech/",
}

WHITESPACE_RE = re.compile(r"\s+")
TRAILING_PUNCT_RE = re.compile(r"[),.;>\]]+$")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    text = re.sub(r"\b(?:Back to top|Copy Permalink)\b", " ", text, flags=re.I)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_url(value: Any) -> str:
    if value is None:
        return ""

    raw = str(value).strip()
    if not raw or raw == "#":
        return ""

    if raw.lower().startswith(("javascript:", "data:")):
        return ""

    if raw.lower().startswith("mailto:"):
        return raw

    raw = urldefrag(raw)[0].strip()
    raw = TRAILING_PUNCT_RE.sub("", raw)
    if not raw:
        return ""

    parsed = urlparse(raw)
    if parsed.netloc in {"service.northeastern.edu", "northeastern.service-now.com"}:
        article_id = parse_qs(parsed.query).get("sysparm_article", [""])[0]
        if article_id.startswith("KB"):
            return (
                "https://service.northeastern.edu/tech"
                f"?id=kb_article_view&sysparm_article={article_id}"
            )

    return raw


def is_noise_url(url: str) -> bool:
    if not url:
        return True

    if url in GENERIC_SERVICE_URLS:
        return True

    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        if not parsed.netloc:
            return True
        if (
            parsed.netloc in {"service.northeastern.edu", "northeastern.service-now.com"}
            and parsed.path.rstrip("/") == "/tech"
        ):
            qs = parse_qs(parsed.query)
            if not qs.get("sysparm_article"):
                return True

    return False


def dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for link in links:
        text = clean_text(link.get("text"))
        url = normalize_url(link.get("url"))
        if not url or is_noise_url(url):
            continue
        if text.lower() in NOISE_LINK_TEXT:
            continue
        if not text:
            text = url.replace("mailto:", "")
        key = (text, url)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "url": url})
    return out


def normalize_link(raw_link: Any) -> dict[str, str] | None:
    if not isinstance(raw_link, dict):
        return None

    text = clean_text(
        raw_link.get("text")
        or raw_link.get("title")
        or raw_link.get("label")
        or raw_link.get("name")
    )
    url = normalize_url(
        raw_link.get("url") or raw_link.get("href") or raw_link.get("link")
    )

    if not url or is_noise_url(url):
        return None
    if text.lower() in NOISE_LINK_TEXT:
        return None
    if not text:
        text = url.replace("mailto:", "")

    return {"text": text, "url": url}


def normalize_categories(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        items = value
    else:
        text = str(value)
        if " - " in text and "," not in text:
            items = text.split(" - ")
        else:
            items = text.split(",")

    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        category = clean_text(item)
        if not category or category in seen:
            continue
        seen.add(category)
        out.append(category)
    return out


def normalize_related_articles(value: Any, self_title: str) -> list[dict[str, Any]]:
    items: list[Any]
    if value is None:
        items = []
    elif isinstance(value, list):
        items = value
    else:
        items = [part.strip() for part in str(value).split(";") if part.strip()]

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    self_key = clean_text(self_title).lower()

    for item in items:
        if isinstance(item, dict):
            title = clean_text(item.get("title") or item.get("text") or item.get("name"))
            url = normalize_url(item.get("url") or item.get("href") or item.get("link"))
        else:
            title = clean_text(item)
            url = ""

        if not title or title.lower() == self_key:
            continue

        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "url": url or None})

    return out


def clean_steps(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        step = clean_text(item)
        if not step or step in seen:
            continue
        seen.add(step)
        out.append(step)
    return out


def normalize_section(section: Any) -> dict[str, Any] | None:
    if not isinstance(section, dict):
        return None

    raw_heading = clean_text(section.get("heading") or section.get("title") or "")
    raw_text = clean_text(section.get("text") or section.get("body") or "")
    raw_steps = clean_steps(section.get("steps"))
    raw_links = dedupe_links(
        [
            normalized
            for normalized in (
                normalize_link(link) for link in (section.get("links") or [])
            )
            if normalized
        ]
    )

    heading_lower = raw_heading.lower()
    if heading_lower in NOISE_SECTION_HEADINGS:
        return None

    if heading_lower in NOISE_SECTION_PLACEHOLDERS and not raw_text and not raw_steps:
        return None

    if not raw_heading and not raw_text and not raw_steps and not raw_links:
        return None

    return {
        "heading": raw_heading,
        "text": raw_text,
        "steps": raw_steps,
        "links": raw_links,
    }


def normalize_sections(value: Any, fallback_text: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        raw_sections = value
    else:
        raw_sections = []

    sections: list[dict[str, Any]] = []
    for raw in raw_sections:
        normalized = normalize_section(raw)
        if not normalized:
            continue

        if not normalized["heading"]:
            if not sections:
                normalized["heading"] = "Introduction"
                sections.append(normalized)
            else:
                previous = sections[-1]
                merged_text = " ".join(
                    part
                    for part in (previous.get("text", ""), normalized.get("text", ""))
                    if part
                ).strip()
                previous["text"] = merged_text
                previous["steps"] = clean_steps(previous.get("steps", []) + normalized["steps"])
                previous["links"] = dedupe_links(previous.get("links", []) + normalized["links"])
            continue

        sections.append(normalized)

    if not sections and fallback_text:
        sections.append(
            {
                "heading": "Introduction",
                "text": fallback_text,
                "steps": [],
                "links": [],
            }
        )

    return sections


def normalize_doc(raw_doc: dict[str, Any], source_file: str) -> dict[str, Any]:
    article_id = clean_text(raw_doc.get("article_id") or raw_doc.get("kb_id"))
    title = clean_text(raw_doc.get("title") or raw_doc.get("short_description"))
    source_url = normalize_url(raw_doc.get("source_url"))
    article_url = normalize_url(raw_doc.get("article_url") or raw_doc.get("url"))

    if not article_url and article_id:
        article_url = (
            "https://service.northeastern.edu/tech"
            f"?id=kb_article_view&sysparm_article={article_id}"
        )

    plain_text = clean_text(raw_doc.get("plain_text"))
    sections = normalize_sections(raw_doc.get("sections"), fallback_text=plain_text)

    section_links: list[dict[str, str]] = []
    for section in sections:
        section["links"] = dedupe_links(section.get("links", []))
        section_links.extend(section["links"])

    top_links = dedupe_links(
        [
            normalized
            for normalized in (
                normalize_link(link) for link in (raw_doc.get("links") or [])
            )
            if normalized
        ]
        + section_links
    )

    normalized = {
        "article_id": article_id,
        "title": title,
        "url": article_url,
        "article_url": article_url,
        "source_url": source_url or article_url,
        "doc_type": clean_text(raw_doc.get("doc_type")) or "kb_article",
        "source_system": clean_text(raw_doc.get("source_system")),
        "source_export": source_file,
        "updated_at": clean_text(raw_doc.get("updated_at")),
        "plain_text": plain_text,
        "body_html": raw_doc.get("body_html") or "",
        "sections": sections,
        "links": top_links,
        "categories": normalize_categories(raw_doc.get("categories")),
        "related_articles": normalize_related_articles(raw_doc.get("related_articles"), title),
    }

    if not normalized["plain_text"]:
        normalized["plain_text"] = " ".join(
            sec.get("text", "") for sec in normalized["sections"] if sec.get("text")
        ).strip()

    return normalized


def doc_score(doc: dict[str, Any]) -> int:
    return (
        len(doc.get("plain_text") or "")
        + len(doc.get("body_html") or "")
        + len(doc.get("sections") or []) * 100
        + len(doc.get("links") or []) * 25
        + len(doc.get("related_articles") or []) * 10
    )


def merge_docs(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if doc_score(incoming) > doc_score(existing):
        primary = dict(incoming)
        secondary = existing
    else:
        primary = dict(existing)
        secondary = incoming

    exports = []
    for candidate in (
        existing.get("source_exports"),
        [existing.get("source_export")] if existing.get("source_export") else [],
        incoming.get("source_exports"),
        [incoming.get("source_export")] if incoming.get("source_export") else [],
    ):
        if not candidate:
            continue
        for item in candidate:
            if item and item not in exports:
                exports.append(item)

    categories = []
    for value in (primary.get("categories", []), secondary.get("categories", [])):
        for item in value:
            if item not in categories:
                categories.append(item)

    related = normalize_related_articles(
        primary.get("related_articles", []) + secondary.get("related_articles", []),
        primary.get("title", ""),
    )

    links = dedupe_links(primary.get("links", []) + secondary.get("links", []))

    primary["categories"] = categories
    primary["related_articles"] = related
    primary["links"] = links
    primary["source_exports"] = exports
    primary["source_export"] = exports[0] if exports else primary.get("source_export")
    return primary


def load_raw_docs(in_dir: Path, pattern: str) -> dict[str, dict[str, Any]]:
    docs_by_id: dict[str, dict[str, Any]] = {}

    for fp in sorted(in_dir.glob(pattern)):
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Failed to parse {fp}: {exc}") from exc

        if not isinstance(payload, list):
            raise RuntimeError(f"Expected a JSON array in {fp}")

        for raw_doc in payload:
            if not isinstance(raw_doc, dict):
                continue

            normalized = normalize_doc(raw_doc, fp.name)
            article_id = normalized.get("article_id")
            if not article_id:
                continue

            if article_id in docs_by_id:
                docs_by_id[article_id] = merge_docs(docs_by_id[article_id], normalized)
            else:
                docs_by_id[article_id] = normalized

    return docs_by_id


def write_processed_docs(docs_by_id: dict[str, dict[str, Any]], out_dir: Path, prune: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    target_ids = set(docs_by_id.keys())

    if prune:
        for fp in out_dir.glob("*.json"):
            if fp.stem not in target_ids:
                fp.unlink()

    for article_id, doc in sorted(docs_by_id.items()):
        out_path = out_dir / f"{article_id}.json"
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", default="data/raw")
    ap.add_argument("--pattern", default="*_kb.json")
    ap.add_argument("--out_dir", default="data/processed/kb_json")
    ap.add_argument("--prune", action="store_true")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)

    if not in_dir.exists():
        print(f"[FAIL] Raw KB directory not found: {in_dir}")
        return 1

    docs_by_id = load_raw_docs(in_dir, args.pattern)
    if not docs_by_id:
        print(f"[FAIL] No raw KB documents found in {in_dir} matching {args.pattern}")
        return 1

    write_processed_docs(docs_by_id, out_dir, prune=args.prune)

    print(f"Wrote {len(docs_by_id)} processed KB JSON files to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
