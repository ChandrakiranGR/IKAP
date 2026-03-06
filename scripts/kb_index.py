#!/usr/bin/env python3
import json, csv
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
        heads = []
        for s in doc.get("sections", []):
            if isinstance(s, dict):
                h = (s.get("heading") or "").strip()
                if h:
                    heads.append(h)
        rows.append(
            {
                "article_id": aid,
                "title": title,
                "headings": " | ".join(heads[:8]),
                "json_file": fp.name,
            }
        )

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["article_id", "title", "headings", "json_file"]
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {OUT} with {len(rows)} KB records")


if __name__ == "__main__":
    main()
