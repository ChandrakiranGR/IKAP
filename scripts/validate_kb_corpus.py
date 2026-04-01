#!/usr/bin/env python3
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


GENERIC_SERVICE_URL_RE = re.compile(
    r"^https://(?:service\.northeastern\.edu|northeastern\.service-now\.com)/tech/?$"
)


def sample_join(items: list[str], limit: int = 8) -> str:
    if not items:
        return "None"
    head = items[:limit]
    if len(items) > limit:
        head.append("...")
    return ", ".join(head)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb_dir", default="data/processed/kb_json")
    args = ap.parse_args()

    kb_dir = Path(args.kb_dir)
    if not kb_dir.exists():
        print(f"[FAIL] KB directory not found: {kb_dir}")
        sys.exit(1)

    files = sorted(kb_dir.glob("*.json"))
    if not files:
        print(f"[FAIL] No KB JSON files found in: {kb_dir}")
        sys.exit(1)

    totals = Counter()
    bad_json = []
    missing_title = []
    missing_url = []
    weak_article_url = []
    no_sections = []
    no_step_sections = []
    no_links = []
    generic_only_links = []

    for fp in files:
        totals["files"] += 1

        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            bad_json.append(fp.name)
            continue

        article_id = (doc.get("article_id") or fp.stem).strip()
        title = (doc.get("title") or "").strip()
        article_url = (doc.get("url") or doc.get("article_url") or "").strip()
        links = doc.get("links", []) or []
        sections = doc.get("sections", []) or []
        step_sections = [
            s
            for s in sections
            if isinstance(s, dict) and isinstance(s.get("steps"), list) and s["steps"]
        ]

        if title:
            totals["has_title"] += 1
        else:
            missing_title.append(article_id)

        if article_url:
            totals["has_url"] += 1
            if "kb_article_view" in article_url and article_id in article_url:
                totals["canonical_article_url"] += 1
            elif article_id in article_url:
                totals["article_id_in_url"] += 1
            else:
                weak_article_url.append(article_id)
        else:
            missing_url.append(article_id)

        if sections:
            totals["has_sections"] += 1
        else:
            no_sections.append(article_id)

        if step_sections:
            totals["has_step_sections"] += 1
            totals["step_sections_total"] += len(step_sections)
        else:
            no_step_sections.append(article_id)

        if links:
            totals["has_links"] += 1
            totals["links_total"] += len(links)
            normalized_urls = [(link.get("url") or "").strip() for link in links]
            non_generic = [
                url for url in normalized_urls if url and not GENERIC_SERVICE_URL_RE.match(url)
            ]
            if not non_generic:
                generic_only_links.append(article_id)
        else:
            no_links.append(article_id)

        totals["sections_total"] += len(sections)

    if bad_json:
        print(f"[FAIL] Invalid JSON files: {sample_join(bad_json)}")
        sys.exit(1)

    print(f"KB files scanned: {totals['files']}")
    print(f"Articles with title: {totals['has_title']}/{totals['files']}")
    print(f"Articles with direct URL: {totals['has_url']}/{totals['files']}")
    print(
        "Articles with canonical article URL: "
        f"{totals['canonical_article_url']}/{totals['files']}"
    )
    print(f"Articles with sections: {totals['has_sections']}/{totals['files']}")
    print(
        "Articles with step-bearing sections: "
        f"{totals['has_step_sections']}/{totals['files']}"
    )
    print(
        "Average sections per article: "
        f"{totals['sections_total'] / max(totals['files'], 1):.2f}"
    )
    print(
        "Average extracted links per article: "
        f"{totals['links_total'] / max(totals['files'], 1):.2f}"
    )
    print(
        "Average step sections per article: "
        f"{totals['step_sections_total'] / max(totals['files'], 1):.2f}"
    )

    print("\nReview warnings:")
    print(f"- Missing title: {len(missing_title)} ({sample_join(missing_title)})")
    print(f"- Missing direct URL: {len(missing_url)} ({sample_join(missing_url)})")
    print(
        f"- Weak/non-article URL: {len(weak_article_url)} "
        f"({sample_join(weak_article_url)})"
    )
    print(f"- Missing sections: {len(no_sections)} ({sample_join(no_sections)})")
    print(
        f"- No extracted steps: {len(no_step_sections)} "
        f"({sample_join(no_step_sections)})"
    )
    print(f"- No extracted links: {len(no_links)} ({sample_join(no_links)})")
    print(
        f"- Only generic links: {len(generic_only_links)} "
        f"({sample_join(generic_only_links)})"
    )

    print("\n[OK] KB corpus validation completed.")


if __name__ == "__main__":
    main()
