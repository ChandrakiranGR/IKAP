#!/usr/bin/env python3
"""
KB HTML -> JSON converter (offline, no API).

Reads:  data/raw/kb_html/*.html
Writes: data/processed/kb_json/*.json

Key feature:
- If filename doesn't contain KB#####, the script will try to extract KB#####
  from the HTML content (common in ServiceNow links/params).
"""

import argparse
import csv
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

DEFAULT_SOURCE_SYSTEM = "Northeastern IT Services KB"
DEFAULT_DOC_TYPE = "kb_article"

KB_ID_RE = re.compile(r"\bKB\d{6,10}\b", re.IGNORECASE)
KB_IN_PARAM_RE = re.compile(r"sysparm_article=(KB\d{6,10})", re.IGNORECASE)


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def guess_article_id_from_filename(name: str) -> str:
    m = KB_ID_RE.search(name)
    return m.group(0).upper() if m else ""


def guess_article_id_from_html(raw_html: str) -> str:
    """
    Try to find KB id from:
    1) sysparm_article=KBxxxx
    2) any KBxxxx occurrences
    Prefer the sysparm_article match if present.
    """
    m = KB_IN_PARAM_RE.search(raw_html)
    if m:
        return m.group(1).upper()

    m2 = KB_ID_RE.search(raw_html)
    if m2:
        return m2.group(0).upper()

    return ""


def load_soup(html_path: Path) -> BeautifulSoup:
    raw = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "lxml")

    # remove scripts/styles/noscript (noise + possible embedded config)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return soup


def extract_title(soup: BeautifulSoup) -> str:
    # Try common KB title patterns first
    # 1) h1
    h1 = soup.find("h1")
    if h1:
        t = clean_text(h1.get_text(" "))
        if t:
            return t

    # 2) any h2 that looks like a KB title header
    h2s = soup.find_all("h2")
    for h2 in h2s:
        t = clean_text(h2.get_text(" "))
        if t and "IT Services" not in t and len(t) > 8:
            return t

    # 3) <title>
    if soup.title:
        return clean_text(soup.title.get_text(" "))

    return ""


def extract_sections(soup: BeautifulSoup):
    """
    Heuristic extraction:
    - Use headings (h1/h2/h3) as section boundaries
    - ordered lists -> steps
    - unordered lists -> bullets
    - paragraphs -> text
    """
    headings = soup.find_all(["h1", "h2", "h3"])
    sections = []

    if not headings:
        body_text = clean_text(soup.get_text(" "))
        if body_text:
            sections.append({"heading": "Content", "text": body_text})
        return sections

    for h in headings:
        heading = clean_text(h.get_text(" "))
        if not heading:
            continue

        # Collect siblings until next heading
        content_nodes = []
        node = h.next_sibling
        while node and not (getattr(node, "name", None) in ["h1", "h2", "h3"]):
            if getattr(node, "get_text", None):
                content_nodes.append(node)
            node = node.next_sibling

        steps, bullets, texts = [], [], []

        for n in content_nodes:
            # ordered list => steps
            for ol in getattr(n, "find_all", lambda *_: [])("ol"):
                for li in ol.find_all("li"):
                    t = clean_text(li.get_text(" "))
                    if t:
                        steps.append(t)

            # unordered list => bullets
            for ul in getattr(n, "find_all", lambda *_: [])("ul"):
                for li in ul.find_all("li"):
                    t = clean_text(li.get_text(" "))
                    if t:
                        bullets.append(t)

            # paragraphs => text
            for p in getattr(n, "find_all", lambda *_: [])(["p"]):
                t = clean_text(p.get_text(" "))
                if t:
                    texts.append(t)

        # fallback raw text if nothing found
        if not steps and not bullets and not texts:
            raw_text = clean_text(
                " ".join(
                    clean_text(x.get_text(" "))
                    for x in content_nodes
                    if getattr(x, "get_text", None)
                )
            )
            if raw_text:
                texts.append(raw_text)

        sec = {"heading": heading}
        if steps:
            sec["steps"] = steps
        elif bullets:
            sec["bullets"] = bullets
        elif texts:
            sec["text"] = " ".join(texts)

        if len(sec) > 1:
            sections.append(sec)

    return sections


def load_manifest(manifest_path: str):
    """
    Optional enrichment. Manifest can be empty; script still works.
    Expected columns (any subset is fine):
    article_id,title,category,url,revised_by,last_updated,source_html_file
    """
    manifest = {}
    if not manifest_path:
        return manifest

    mp = Path(manifest_path)
    if not mp.exists():
        return manifest

    with mp.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            aid = (row.get("article_id") or "").strip().upper()
            if aid:
                manifest[aid] = row
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in", dest="inp", required=True, help="Input folder containing KB HTML files"
    )
    ap.add_argument(
        "--out", dest="out", required=True, help="Output folder for JSON files"
    )
    ap.add_argument(
        "--manifest",
        dest="manifest",
        default="",
        help="Optional kb_manifest.csv to enrich metadata",
    )
    args = ap.parse_args()

    inp = Path(args.inp)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(args.manifest)

    html_files = sorted(inp.glob("*.html"))
    if not html_files:
        raise SystemExit(f"No .html files found in {inp}")

    for hp in html_files:
        raw_html = hp.read_text(encoding="utf-8", errors="ignore")

        # 1) try filename KB id
        article_id = guess_article_id_from_filename(hp.name)

        # 2) fallback: try inside HTML content
        if not article_id:
            article_id = guess_article_id_from_html(raw_html)

        soup = load_soup(hp)
        title = extract_title(soup)

        meta = manifest.get(article_id, {}) if article_id else {}

        doc = {
            "source_system": DEFAULT_SOURCE_SYSTEM,
            "doc_type": DEFAULT_DOC_TYPE,
            "article_id": article_id,
            "title": meta.get("title", "") or title,
            "category": meta.get("category", "") or "",
            "revised_by": meta.get("revised_by", "") or "",
            "url": meta.get("url", "") or "",
            "sections": extract_sections(soup),
            "source_file": hp.name,
        }

        # Output filename
        out_name = f"{article_id}.json" if article_id else f"{hp.stem}.json"
        out_path = out / out_name

        out_path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Wrote {out_path.name}")

    print("Done.")


if __name__ == "__main__":
    main()
