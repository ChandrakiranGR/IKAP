#!/usr/bin/env python3
"""
Redact PII across ALL columns of a ServiceNow incident CSV export (offline).

Catches:
- Emails, phones, IPv4, MAC, URLs (incl. naked domains with paths), long numeric IDs (7+), basic DOB patterns
- Ticket numbers: INC########, RITM########, REQ########, TASK########, CHG########
- Labeled Student ID / NUID numeric values
- Username fields like "Username: xxx" / "user name: xxx"
- Work note author names ("Work Note by <name> (")
- "Lastname, Firstname" patterns
- "Name: <value>" and "Agent: <value>" fields (force-redacted)
- Greeting names like "Hi Akanksha," / "Hello John," / "Dear Mary,"
- In-line intros (robust): "My name is <anything...>" (handles long names + lowercase + hyphens)
- "This is First Last ..." patterns
- Signature block names near org/title lines and around separators
- Optional cleanup: cid:image... references (noise)

Usage:
  python3 scripts/redact_incidents_allcols.py --in <input.csv> --out <output.csv>
"""

import argparse
import re
from pathlib import Path
import pandas as pd

# ---------- Base PII patterns ----------
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?"
    r"(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"
)

IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")

URL_RE = re.compile(
    r"\b(?:https?://\S+|www\.\S+|[A-Za-z0-9.-]+\.[A-Za-z]{2,}/\S+)",
    re.IGNORECASE,
)

LONG_ID_RE = re.compile(r"\b\d{7,}\b")
DOB_RE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")

TICKET_RE = re.compile(r"\b(?:INC|RITM|REQ|TASK|CHG)\d{6,10}\b", re.IGNORECASE)
CID_RE = re.compile(r"\bcid:[^\s,;\"']+", re.IGNORECASE)

STUDENT_ID_LABEL_RE = re.compile(r"(?im)\b(student\s*id|nuid)\s*[:#]?\s*\d+\b")

# ---------- Helpdesk-field patterns ----------
USERNAME_FIELD_RE = re.compile(r"(?im)\b(username|user\s*name)\s*:\s*([^\n\r,]+)")
WORK_NOTE_BY_RE = re.compile(r"(?im)\bWork Note by\s+([^\(\n\r]+)\(")

NAME_AFTER_DASH_COMMA_RE = re.compile(
    r"(?m)(-\s*)([A-Z][A-Za-z'’\-\uFFFD]+,\s*[A-Z][A-Za-z'’\-\uFFFD]+)(\s*\()"
)
NAME_COMMA_RE = re.compile(
    r"(?m)\b([A-Z][A-Za-z'’\-\uFFFD]+,\s*[A-Z][A-Za-z'’\-\uFFFD]+)\b"
)

NAME_LABEL_RE = re.compile(r"(?im)\bname\s*:\s*[^\n\r,]+")
AGENT_LABEL_RE = re.compile(r"(?im)\bagent\s*:\s*[^\n\r,]+")

# ----- Greetings (case-insensitive greeting word only) -----
NAME_TOKEN = r"[A-Z][A-Za-z'’\-\uFFFD]+"
GREETING_RE = re.compile(
    rf"(?m)^\s*((?i:hi|hello|dear))\s+({NAME_TOKEN})(?:\s+{NAME_TOKEN})?\s*([,:])"
)
NON_PERSON_GREETING_WORDS = {"there", "team", "everyone", "all"}

SIGNOFF_WORDS = {"regards", "best", "sincerely", "thanks", "thank you"}

SIG_ANCHORS = [
    "client experience representative",
    "client support specialist",
    "information technology services",
    "information technology",
    "northeastern university",
    "service desk",
    "it service desk",
    "tech bar",
    "contact us",
]

STOPWORDS_IN_NAME_LINE = {
    "university",
    "services",
    "technology",
    "information",
    "representative",
    "help",
    "desk",
    "library",
    "snell",
    "client",
    "experience",
    "team",
    "its",
    "northeastern",
    "service",
    "desk",
    "office",
    "department",
    "contact",
    "website",
    "support",
    "specialist",
}

PRODUCT_PREFIX_CLEAN_RE = re.compile(
    r"\[REDACTED_NAME\]\s+(Outlook|Windows|Android|iOS|macOS|Duo|Microsoft|Teams|OneDrive|Edge|Chrome|Safari|Zoom|Webex)\b"
)

SAFE_FOLLOW_WORDS = {
    "outlook",
    "windows",
    "android",
    "ios",
    "macos",
    "duo",
    "microsoft",
    "teams",
    "onedrive",
    "edge",
    "chrome",
    "safari",
    "zoom",
    "webex",
    "time",
    "additional",
    "comments",
    "work",
    "notes",
}

# ----- In-line introductions -----
# Robust freeform "my name is ..." (handles long names + lowercase + hyphens)
# Stops at punctuation/newline or common continuation keywords.
MY_NAME_FREEFORM_RE = re.compile(
    r"\b((?i:my name is))\s+(.{1,120}?)"
    r"(?=\s*(?:"
    r"[,.;:\(\)\n]|"
    r"with\b|bearing\b|from\b|and\b|"
    r"i\b|l\b|we\b|"
    r"got\b|have\b|has\b|had\b|am\b|is\b|are\b|was\b|were\b|"
    r"can\b|could\b|would\b|may\b|please\b|"
    r"(?i:thanks\b|thank\b)|"
    r"$"
    r"))"
)
EMAIL_PARTIAL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\b")
# "this is First Last <role>" (keep this stricter to avoid matching "This is in a classroom")
INTRO_WITH_ROLE_RE = re.compile(
    rf"\b((?i:this is))\s+({NAME_TOKEN})\s+({NAME_TOKEN})(?=\s+(?i:client|information|it|service|support|desk|representative|specialist)\b)"
)

INTRO_THIS_IS_FROM_RE = re.compile(
    rf"\b((?i:this is))\s+({NAME_TOKEN})\s*,\s*(?i:from)\b"
)

IS_NAME_FROM_RE = re.compile(
    rf"\bis\s+({NAME_TOKEN})(?:\s+{NAME_TOKEN})?\s*,\s*(?i:from)\b"
)

INTRO_PLACEHOLDER_RE = re.compile(r"(?im)\bmy name is\s+agent\S*\s+name\b")


def read_csv_safe(path: Path) -> pd.DataFrame:
    for enc in ("utf-8", "cp1252", "latin1"):
        try:
            return pd.read_csv(
                path,
                dtype=str,
                keep_default_na=True,
                encoding=enc,
                encoding_errors="replace",
            )
        except UnicodeDecodeError:
            continue

    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=True,
        encoding="latin1",
        encoding_errors="replace",
        engine="python",
        on_bad_lines="skip",
    )


def _is_name_token(tok: str) -> bool:
    tok = tok.strip().strip(",.;:()[]{}<>\"'")
    if not tok:
        return False
    if not tok[0].isupper():
        return False
    for ch in tok[1:]:
        if ch.isalpha() or ch in ("'", "’", "-", "�"):
            continue
        return False
    return True


def looks_like_name_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if any(ch.isdigit() for ch in s):
        return False
    low = s.lower()
    for w in STOPWORDS_IN_NAME_LINE:
        if w in low:
            return False
    if len(s) > 50:
        return False
    parts = s.split()
    if len(parts) < 2 or len(parts) > 3:
        return False
    return all(_is_name_token(p) for p in parts)


def redact_signature_names_by_signoff(text: str) -> str:
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        token = lines[i].strip().lower().strip(",")
        if token in SIGNOFF_WORDS:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and looks_like_name_line(lines[j]):
                lines[j] = "[REDACTED_NAME]"
    return "\n".join(lines)


def redact_signature_names_by_anchors(text: str) -> str:
    lines = text.splitlines()
    lowers = [ln.lower() for ln in lines]

    for i, low in enumerate(lowers):
        if any(anchor in low for anchor in SIG_ANCHORS):
            for j in range(max(0, i - 4), i):
                if looks_like_name_line(lines[j]):
                    lines[j] = "[REDACTED_NAME]"

    for i, ln in enumerate(lines):
        if re.match(r"^[_\-]{5,}\s*$", ln.strip()):
            for j in [i - 1, i + 1]:
                if 0 <= j < len(lines) and looks_like_name_line(lines[j]):
                    lines[j] = "[REDACTED_NAME]"

    return "\n".join(lines)


def redact_greeting_names(text: str) -> str:
    def repl(m):
        greet = m.group(1)
        first = (m.group(2) or "").strip()
        punct = m.group(3)
        if first.lower() in NON_PERSON_GREETING_WORDS:
            return m.group(0)
        return f"{greet} [REDACTED_NAME]{punct}"

    return GREETING_RE.sub(repl, text)


def redact_inline_introductions(text: str) -> str:
    # Placeholder
    text = INTRO_PLACEHOLDER_RE.sub("my name is [REDACTED_NAME]", text)

    # Robust "my name is <freeform...>"
    text = MY_NAME_FREEFORM_RE.sub(lambda m: f"{m.group(1)} [REDACTED_NAME]", text)

    # this is First Last <role>
    text = INTRO_WITH_ROLE_RE.sub(lambda m: f"{m.group(1)} [REDACTED_NAME]", text)

    # this is Diana, from ...
    text = INTRO_THIS_IS_FROM_RE.sub(
        lambda m: f"{m.group(1)} [REDACTED_NAME], from", text
    )

    # is Diana, from ...
    text = IS_NAME_FROM_RE.sub("is [REDACTED_NAME], from", text)

    return text


def remove_trailing_name_after_redacted(text: str) -> str:
    def repl(m):
        word = m.group(1)
        if word.lower() in SAFE_FOLLOW_WORDS:
            return f"[REDACTED_NAME] {word}"
        return "[REDACTED_NAME]"

    pattern = re.compile(r"\[REDACTED_NAME\]\s+([A-Z][A-Za-z'’\-\uFFFD]+)")
    cur = text
    for _ in range(3):
        new = pattern.sub(repl, cur)
        if new == cur:
            break
        cur = new

    cur = re.sub(
        r"(?im)\b(Name|Agent)\s*:\s*\[REDACTED_NAME\]\s+[A-Z][A-Za-z'’\-\uFFFD]+",
        r"\1: [REDACTED_NAME]",
        cur,
    )
    return cur


def redact_text(val, redact_urls: bool = True):
    if pd.isna(val):
        return val

    t = str(val)

    # 0) Clean noisy CID refs early (prevents @ inside cid:... from tripping email patterns)
    t = CID_RE.sub("[REDACTED_CID]", t)

    # 1) Core PII redactions
    t = EMAIL_RE.sub("[REDACTED_EMAIL]", t)
    t = EMAIL_PARTIAL_RE.sub("[REDACTED_EMAIL]", t)  # catches partial like name@gmail

    t = PHONE_RE.sub("[REDACTED_PHONE]", t)
    t = IPV4_RE.sub("[REDACTED_IP]", t)
    t = MAC_RE.sub("[REDACTED_MAC]", t)

    t = TICKET_RE.sub("[REDACTED_TICKET]", t)

    # labeled IDs first, then generic long IDs
    t = STUDENT_ID_LABEL_RE.sub(lambda m: f"{m.group(1)}: [REDACTED_ID]", t)
    t = LONG_ID_RE.sub("[REDACTED_ID]", t)

    t = DOB_RE.sub("[REDACTED_DOB]", t)

    # 2) URLs (includes naked domains with paths)
    if redact_urls:
        t = URL_RE.sub("[REDACTED_URL]", t)

    # 3) Common structured fields
    t = USERNAME_FIELD_RE.sub(lambda m: f"{m.group(1)}: [REDACTED_USERNAME]", t)
    t = NAME_LABEL_RE.sub("Name: [REDACTED_NAME]", t)
    t = AGENT_LABEL_RE.sub("Agent: [REDACTED_NAME]", t)

    # 4) Work-note author + comma-name patterns
    t = WORK_NOTE_BY_RE.sub("Work Note by [REDACTED_NAME] (", t)
    t = NAME_AFTER_DASH_COMMA_RE.sub(r"\1[REDACTED_NAME]\3", t)
    t = NAME_COMMA_RE.sub("[REDACTED_NAME]", t)

    # 5) Free-text name handling
    t = redact_greeting_names(t)
    t = redact_inline_introductions(t)  # includes robust "my name is ..." handling
    t = redact_signature_names_by_signoff(t)
    t = redact_signature_names_by_anchors(t)
    t = remove_trailing_name_after_redacted(t)

    # 6) Cleanup false positives (product words)
    t = PRODUCT_PREFIX_CLEAN_RE.sub(r"\1", t)

    return t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in", dest="inp", required=True, help="Input incident CSV file"
    )
    parser.add_argument(
        "--out", dest="out", required=True, help="Output redacted CSV file"
    )
    parser.add_argument(
        "--keep_cols",
        nargs="*",
        default=None,
        help="Optional allowlist: keep only these columns (after redaction)",
    )
    parser.add_argument(
        "--drop_cols",
        nargs="*",
        default=None,
        help="Optional denylist: drop these columns before writing output",
    )
    parser.add_argument(
        "--no_url_redact", action="store_true", help="Disable URL redaction"
    )
    args = parser.parse_args()

    inp_path = Path(args.inp)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = read_csv_safe(inp_path)

    if args.drop_cols:
        for c in args.drop_cols:
            if c in df.columns:
                df = df.drop(columns=[c])

    redact_urls = not args.no_url_redact

    for col in df.columns:
        df[col] = df[col].apply(lambda x: redact_text(x, redact_urls=redact_urls))

    if args.keep_cols:
        cols = [c for c in args.keep_cols if c in df.columns]
        df = df[cols]

    df.to_csv(out_path, index=False)
    print(f"Wrote redacted CSV: {out_path}")


if __name__ == "__main__":
    main()
