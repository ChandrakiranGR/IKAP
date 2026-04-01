#!/usr/bin/env python3
import csv
import json
from pathlib import Path

IN_DIR = Path("data/processed/kb_json")
OUT = Path("data/manifests/kb_index.csv")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for fp in sorted(IN_DIR.glob("*.json")):
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        aid = doc.get("article_id") or fp.stem
        title = doc.get("title", "")
        article_url = doc.get("url") or doc.get("article_url") or ""
        links = doc.get("links", []) or []
        sections = doc.get("sections", []) or []
        categories = doc.get("categories", []) or []
        heads = []
        step_section_count = 0
        for s in sections:
            if isinstance(s, dict):
                h = (s.get("heading") or "").strip()
                if h:
                    heads.append(h)
                if s.get("steps"):
                    step_section_count += 1
        rows.append(
            {
                "article_id": aid,
                "title": title,
                "article_url": article_url,
                "section_count": len(sections),
                "step_section_count": step_section_count,
                "link_count": len(links),
                "categories": " | ".join(str(c).strip() for c in categories if str(c).strip()),
                "headings": " | ".join(heads[:8]),
                "source_export": doc.get("source_export", ""),
                "json_file": fp.name,
            }
        )

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "article_id",
                "title",
                "article_url",
                "section_count",
                "step_section_count",
                "link_count",
                "categories",
                "headings",
                "source_export",
                "json_file",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {OUT} with {len(rows)} KB records")


if __name__ == "__main__":
    main()
