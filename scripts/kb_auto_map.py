#!/usr/bin/env python3
import csv
from pathlib import Path

IN_CSV = Path("data/manifests/kb_index.csv")
OUT_CSV = Path("data/manifests/kb_use_case_map.csv")

RULES = {
    "mfa": ["duo", "multi-factor", "mfa", "two-factor", "2fa", "authenticator"],
    "password": [
        "password",
        "reset password",
        "forgot password",
        "change password",
        "password reset",
        "expired password",
        "temporary password",
        "password policy",
        "unlock account",
        "account locked",
    ],
    "account_access": [
        "log in",
        "login",
        "sign in",
        "can't log in",
        "cannot log in",
        "username",
        "change username",
        "update username",
        "northeastern services",
        "single sign-on",
        "sso",
        "student account",
        "faculty/staff username",
        "husky username",
    ],
    "wifi": ["nuwave", "wifi", "wireless", "eduroam", "certificate"],
    "vpn": ["vpn", "globalprotect", "anyconnect", "remote access"],
    "student_portal": [
        "student hub",
        "portal",
        "profile",
        "update personal",
        "contact information",
        "cell phone number",
    ],
    "canvas": [
        "canvas",
        "lms",
        "instructure",
        "speedgrader",
        "gradebook",
        "modules",
        "assignments",
        "quizzes",
        "discussions",
        "attendance",
        "turnitin",
    ],
    "software": [
        "install",
        "download",
        "license",
        "software",
        "activation",
        "vpn client",
    ],
}


def pick_use_case(text: str):
    t = (text or "").lower()
    best = ("other", 0)
    for uc, keys in RULES.items():
        score = sum(1 for k in keys if k in t)
        if score > best[1]:
            best = (uc, score)
    return best[0], best[1]


def main():
    rows = []
    with IN_CSV.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            blob = f"{row.get('title', '')} {row.get('headings', '')}"
            uc, score = pick_use_case(blob)
            rows.append(
                {
                    "article_id": row["article_id"],
                    "use_case": uc,
                    "confidence": score,
                    "notes": "",
                }
            )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["article_id", "use_case", "confidence", "notes"]
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {OUT_CSV} with {len(rows)} mappings")


if __name__ == "__main__":
    main()
