#!/usr/bin/env python3
"""
kb_html_to_json.py

Convert ServiceNow KB HTML exports to structured JSON.

Fixes:
- Correct KB ID detection (canonical/og:url/first sysparm_article)
- Robust section extraction (heading -> until next heading)
- Hyperlink capture (per-section + top-level)
- Fallback when headings exist but text extraction fails
"""

import re
import json
import argparse
from pathlib import Path
from collections import Counter
from urllib.parse import urljoin, urldefrag

from bs4 import BeautifulSoup


# -----------------------------
# Regexes
# -----------------------------
KB_ID_RE = re.compile(r"\bKB\d{7,9}\b", re.IGNORECASE)
SYS_PARM_RE = re.compile(r"sysparm_article=(KB\d{7,9})", re.IGNORECASE)


# -----------------------------
# Helpers
# -----------------------------
def normalize_ws(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def normalize_href(href: str, base_url: str | None) -> str | None:
    href = (href or "").strip()
    if not href:
        return None
    low = href.lower()
    if low.startswith(("javascript:", "mailto:", "tel:")):
        return None
    if base_url:
        href = urljoin(base_url, href)
    href = urldefrag(href)[0]
    return href


def dedupe_links(links: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for l in links or []:
        txt = (l.get("text") or "").strip()
        url = (l.get("url") or "").strip()
        if not url:
            continue
        key = (txt, url)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": txt, "url": url})
    return out


def collect_links(tag, base_url: str | None) -> list[dict]:
    links = []
    for a in tag.find_all("a", href=True):
        txt = a.get_text(" ", strip=True)
        href = normalize_href(a.get("href", ""), base_url)
        if txt and href:
            links.append({"text": txt, "url": href})
    return links


# -----------------------------
# KB ID + URL detection
# -----------------------------
def extract_canonical_url(soup: BeautifulSoup) -> str | None:
    # <link rel="canonical" href="...">
    canon = soup.find("link", rel=lambda x: x and "canonical" in str(x).lower())
    if canon and canon.get("href"):
        return canon["href"].strip()
    return None


def extract_og_url(soup: BeautifulSoup) -> str | None:
    # <meta property="og:url" content="...">
    og = soup.find("meta", attrs={"property": "og:url"})
    if og and og.get("content"):
        return str(og["content"]).strip()
    return None


def pick_article_id(html: str, soup: BeautifulSoup, filename: str) -> str | None:
    """
    IMPORTANT:
    Do NOT choose the 'most common' KB id from the HTML,
    because pages contain related-articles links that will dominate counts.
    """

    # 1) canonical link
    canon = extract_canonical_url(soup)
    if canon:
        m = SYS_PARM_RE.search(canon)
        if m:
            return m.group(1).upper()

    # 2) og:url
    og = extract_og_url(soup)
    if og:
        m = SYS_PARM_RE.search(og)
        if m:
            return m.group(1).upper()

    # 3) FIRST sysparm_article occurrence in full HTML (not most common)
    m = SYS_PARM_RE.search(html)
    if m:
        return m.group(1).upper()

    # 4) fallback: any KB id in HTML (first)
    m = KB_ID_RE.search(html)
    if m:
        return m.group(0).upper()

    # 5) fallback: filename contains KB
    m = KB_ID_RE.search(filename)
    if m:
        return m.group(0).upper()

    return None


# -----------------------------
# Content extraction
# -----------------------------
def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(" ", strip=True)
        if t:
            return t
    if soup.title and soup.title.string:
        return str(soup.title.string).strip()
    return "Untitled KB"


def choose_main_container(soup: BeautifulSoup):
    """
    Heuristic: pick a container with the most meaningful text.
    This helps avoid extracting nav/footer/sidebars.
    """
    candidates = []

    # Semantic containers
    for sel in ["article", "main"]:
        candidates.extend(soup.find_all(sel))

    # ServiceNow-ish / generic content containers
    candidates.extend(
        soup.find_all(
            ["div", "section"],
            attrs={"id": re.compile(r"(kb|article|content|main|body)", re.I)},
        )
    )
    candidates.extend(
        soup.find_all(
            ["div", "section"],
            attrs={"class": re.compile(r"(kb|article|content|main|body)", re.I)},
        )
    )

    # fallback
    if soup.body:
        candidates.append(soup.body)

    def score(tag):
        txt = tag.get_text(" ", strip=True)
        return len(txt)

    return max(candidates, key=score, default=soup.body or soup)


def extract_sections(container, base_url: str | None) -> list[dict]:
    # remove noise
    for noise in container.find_all(
        ["script", "style", "noscript", "nav", "footer", "aside"]
    ):
        noise.decompose()

    headings = container.find_all(["h1", "h2", "h3"])

    # If no headings, single body section
    if not headings:
        full_txt = normalize_ws(container.get_text("\n", strip=True))
        links = dedupe_links(collect_links(container, base_url))
        return [{"heading": "Body", "text": full_txt, "links": links}]

    sections = []

    for i, h in enumerate(headings):
        heading = h.get_text(" ", strip=True)
        if not heading:
            continue

        next_h = headings[i + 1] if (i + 1) < len(headings) else None

        blocks = []
        links = []

        # walk forward until next heading
        for el in h.next_elements:
            if el == next_h:
                break

            if not hasattr(el, "name"):
                continue

            # stop if we hit another heading (safety)
            if el.name in ["h1", "h2", "h3"]:
                break

            # collect text from common content blocks
            if el.name in ["p", "li", "td", "th", "pre", "code", "blockquote"]:
                t = normalize_ws(el.get_text("\n", strip=True))
                if t:
                    blocks.append(t)
                links.extend(collect_links(el, base_url))

        sec_text = normalize_ws("\n\n".join(blocks))
        sections.append(
            {
                "heading": heading,
                "text": sec_text,
                "links": dedupe_links(links),
            }
        )

    # Fallback: headings exist but we extracted nothing
    total = sum(len((s.get("text") or "").strip()) for s in sections)
    if total == 0:
        full_txt = normalize_ws(container.get_text("\n", strip=True))
        links = dedupe_links(collect_links(container, base_url))
        return [{"heading": "Body", "text": full_txt, "links": links}]

    return sections


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in_dir", default="data/raw/kb_html", help="Folder containing *.html exports"
    )
    ap.add_argument(
        "--out_dir",
        default="data/processed/kb_json",
        help="Folder to write KB JSON files",
    )
    ap.add_argument(
        "--base_url",
        default="https://service.northeastern.edu",
        help="Used to resolve relative links",
    )
    ap.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing JSON files"
    )
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(in_dir.glob("*.html"))
    if not html_files:
        raise SystemExit(f"No .html files found in: {in_dir}")

    processed_html = 0
    wrote_unique = 0
    overwritten = 0
    skipped = 0
    missing_id = 0

    for fp in html_files:
        processed_html += 1
        html = fp.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")

        article_id = pick_article_id(html, soup, fp.name)
        if not article_id:
            print(f"[SKIP] Could not detect KB ID for: {fp.name}")
            missing_id += 1
            continue

        title = extract_title(soup)
        container = choose_main_container(soup)
        sections = extract_sections(container, args.base_url)

        # Roll up top-level links
        all_links = []
        for s in sections:
            all_links.extend(s.get("links", []))
        all_links = dedupe_links(all_links)

        # Prefer canonical/og URL if present
        url = extract_canonical_url(soup) or extract_og_url(soup)
        if url:
            url = normalize_href(url, None)

        kb_obj = {
            "article_id": article_id,
            "doc_type": "kb_article",
            "title": title,
            "source_system": "ServiceNow",
            "source_file": fp.name,
            "url": url,
            "sections": sections,
            "links": all_links,
        }

        out_path = out_dir / f"{article_id}.json"
        if out_path.exists() and not args.overwrite:
            skipped += 1
            continue

        if out_path.exists() and args.overwrite:
            overwritten += 1

        out_path.write_text(
            json.dumps(kb_obj, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        wrote_unique += 1

    # Actual unique count on disk
    actual_json = len(list(out_dir.glob("*.json")))

    print(f"Processed HTML files: {processed_html}")
    print(f"Wrote/updated JSON:   {wrote_unique}")
    print(f"Overwritten (overwrite): {overwritten}")
    print(f"Skipped (no overwrite):  {skipped}")
    print(f"Missing KB ID:           {missing_id}")
    print(f"JSON files on disk:   {actual_json}")
    print(f"Output dir: {out_dir}")


if __name__ == "__main__":
    main()
