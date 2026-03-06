#!/usr/bin/env python3
import json, csv, re
from pathlib import Path

KB_DIR = Path("data/processed/kb_json")
MAP_CSV = Path("data/manifests/kb_use_case_map.csv")

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

CATEGORY_MAP = {
    "mfa": "MFA",
    "wifi": "Network",
    "vpn": "Remote Access",
    "password": "Password",  # optional but clearer
    "account_access": "Account Access",
    "software": "Software",
    "student_portal": "Student Portal",
    "canvas": "Canvas (LMS)",
}


def strip_urls(s: str) -> str:
    return URL_RE.sub("[URL]", s)


def load_kb_ids(use_case: str):
    kb_ids = []
    with MAP_CSV.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("use_case") or "").strip() == use_case:
                kb_ids.append((row.get("article_id") or "").strip())
    return [x for x in kb_ids if x]


def pick_steps(doc: dict):
    sections = doc.get("sections", [])

    # First: any section with steps
    for s in sections:
        if (
            isinstance(s, dict)
            and isinstance(s.get("steps"), list)
            and len(s["steps"]) > 0
        ):
            return [strip_urls(str(x)).strip() for x in s["steps"] if str(x).strip()]

    # Fallback: choose steps from headings likely to contain procedures
    for s in sections:
        if isinstance(s, dict) and isinstance(s.get("steps"), list):
            h = (s.get("heading") or "").lower()
            if any(
                k in h
                for k in [
                    "how",
                    "enroll",
                    "setup",
                    "set up",
                    "install",
                    "connect",
                    "configure",
                    "steps",
                ]
            ):
                steps = [
                    strip_urls(str(x)).strip() for x in s["steps"] if str(x).strip()
                ]
                if steps:
                    return steps

    return []


def make_queries(title: str):
    t = (title or "").strip().rstrip("?")
    if not t:
        return []
    return [
        f"{t}?",
        f"How do I {t.lower()}?",
        f"I need help with {t.lower()}. What should I do?",
        f"Can you give me step-by-step instructions for {t.lower()}?",
    ]


def main(use_case: str, out_path: str, n_per_kb: int):
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    kb_ids = set(load_kb_ids(use_case))
    category = CATEGORY_MAP.get(use_case, use_case.upper())

    written = 0
    with out.open("w", encoding="utf-8") as f:
        for fp in sorted(KB_DIR.glob("*.json")):
            doc = json.loads(fp.read_text(encoding="utf-8"))
            aid = (doc.get("article_id") or fp.stem).strip()
            if aid not in kb_ids:
                continue

            title = doc.get("title", "") or aid
            steps = pick_steps(doc)
            if not steps:
                continue

            steps = steps[:5]  # keep consistent output
            queries = make_queries(title)[:n_per_kb]

            for i, q in enumerate(queries, start=1):
                rec = {
                    "id": f"{use_case}-typ-{aid}-{i:02d}",
                    "use_case": use_case,
                    "case_type": "typical",
                    "user_query": q,
                    "expected_output": {
                        "category": category,
                        "steps": steps,
                        "escalation": "Contact Northeastern IT support and share your device/OS, what step you got stuck on, and any error message shown.",
                    },
                    "guardrails": {
                        "no_urls": True,
                        "no_portal_navigation": True,
                        "no_policy_claims": True,
                    },
                    "source": {
                        "kb_ids": [aid],
                        "incident_refs": [],
                        "notes": "Generated from KB JSON steps; URLs stripped.",
                    },
                    "tags": [use_case, "kb_based"],
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1

    print(f"Wrote {written} examples to {out}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--use_case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n_per_kb", type=int, default=2)
    args = ap.parse_args()
    main(args.use_case, args.out, args.n_per_kb)
