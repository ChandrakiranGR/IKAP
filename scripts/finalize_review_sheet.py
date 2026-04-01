#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path


VALID_FINAL_STATUSES = {"approved", "approved_with_edits", "edited", "rejected"}

ESCALATION_BLOCK = (
    "If this does not resolve your issue: Contact Northeastern IT Support and include:\n"
    "- Your device/OS\n"
    "- The step where the issue occurred\n"
    "- Any error message shown"
)


def load_rows(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_answer(category: str, title: str, reference_url: str, steps: list[str]) -> str:
    step_lines = "\n".join(f"{idx}. {step}" for idx, step in enumerate(steps, start=1))
    return (
        f"Category: {category}\n"
        "Clarifying question: None\n"
        "Steps:\n"
        f"{step_lines}\n"
        "References:\n"
        f"- {title}: {reference_url}\n"
        f"{ESCALATION_BLOCK}"
    )


OVERRIDES = {
    "KB0012541": {
        "question": "How do I access Abaqus?",
        "answer": format_answer(
            "Software access",
            "How do I access Abaqus?",
            "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0012541",
            [
                "Open the Abaqus Student Edition page on the 3DS Education website.",
                "Select 'DOWNLOAD FOR FREE'.",
                "Sign in with your '3DEXPERIENCE ID' or 'SOLIDWORKS ID'.",
                "If this is your first visit, create a new '3DEXPERIENCE ID'.",
                "Scroll to the 'Abaqus Student Edition Download' section.",
                "Download the version you need.",
                "Follow the installation instructions provided on the vendor site.",
            ],
        ),
        "status": "approved_with_edits",
        "notes": "Auto-curated to remove raw URLs from steps.",
    },
    "KB000017928": {
        "question": "How do I set up differentiated due dates in Canvas?",
        "answer": format_answer(
            "Canvas and teaching tools",
            "How do I set up differentiated due dates in Canvas?",
            "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB000017928",
            [
                "Open the assignment, quiz, or discussion in Canvas.",
                "Select the activity that needs differentiated due dates.",
                "Select Edit.",
                "Select 'Manage Due Dates and Assign To'.",
                "Under 'Assign to', select Add.",
                "Type the student or section name and select the correct match when it appears.",
                "If you remove the default class or section, make sure everyone who should still see the activity remains assigned.",
                "Enter the due date and availability dates.",
                "Select Save or 'Save & Publish'.",
            ],
        ),
        "status": "approved_with_edits",
        "notes": "Auto-curated to split a long instructional note into a cleaner sequence.",
    },
    "KB000018093": {
        "question": "What is NUwave and who can use it?",
        "answer": format_answer(
            "WiFi and network connectivity",
            "What is NUwave?",
            "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB000018093",
            [
                "Use NUwave for secure Northeastern wireless access on the Boston campus.",
                "Connect with your Northeastern username and password.",
                "Use NUwave if you are an instructor, student, staff member, or sponsored account holder.",
                "Use NUwave on laptops, phones, and other personal devices that support WPA2-Enterprise or 802.1x authentication.",
                "Expect NUwave to be available in academic buildings, administrative locations, and university-owned residence halls.",
            ],
        ),
        "status": "approved_with_edits",
        "notes": "Auto-curated to convert list fragments into a usable explanatory answer.",
    },
    "KB0015064": {
        "question": "How do I sync Canvas calendar to Outlook?",
        "answer": format_answer(
            "Canvas and teaching tools",
            "How do I sync Canvas calendar to Outlook?",
            "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0015064",
            [
                "Open Canvas and select the Calendar icon.",
                "Select 'Calendar Feed' at the bottom right of the page and copy the feed link.",
                "Open Outlook and select the Calendar icon.",
                "Select 'Add calendar'.",
                "Select 'Subscribe from web'.",
                "Paste the Canvas calendar feed link.",
                "Add a calendar name, icon, and color if you want, then select Import.",
                "Check Outlook for imported Canvas events, assignments, and appointments.",
                "Allow up to 24 hours for Canvas updates to appear in Outlook.",
            ],
        ),
        "status": "approved_with_edits",
        "notes": "Auto-curated from a noisy source record to restore the intended step order.",
    },
    "KB0014253": {
        "question": "How do I use Turnitin's quick submit as a faculty?",
        "answer": format_answer(
            "Canvas and teaching tools",
            "How do I use Turnitin's quick submit as a faculty?",
            "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0014253",
            [
                "If you cannot sign in to Turnitin, select 'Forgot your password?' and complete the emailed reset steps.",
                "Log in to Turnitin.",
                "Select 'User Info' from the top navigation menu.",
                "In 'User Information/Account Settings', set 'Activate quick submit' to Yes and select Submit.",
                "Open the 'Quick Submit' tab and select Submit.",
                "Choose the database or databases to check, then enter the author's name and submission title.",
                "Upload the file, preview the submission, and select Confirm.",
                "To review the similarity report, return to the 'Quick Submit' tab and select the Similarity percentage.",
            ],
        ),
        "status": "approved_with_edits",
        "notes": "Auto-curated to split merged Turnitin sections into distinct steps.",
    },
}


def is_terminal_status(value: str) -> bool:
    return (value or "").strip().lower() in VALID_FINAL_STATUSES


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review_sheet", default="data/dataset/review_sheet.csv")
    args = ap.parse_args()

    path = Path(args.review_sheet)
    fieldnames, rows = load_rows(path)

    approved = 0
    edited = 0

    for row in rows:
        article_id = row.get("article_id", "")
        status = (row.get("review_status") or "").strip().lower()

        if is_terminal_status(status):
            continue

        override = OVERRIDES.get(article_id)
        if override:
            row["edited_question"] = override["question"]
            row["edited_answer"] = override["answer"]
            row["review_status"] = override["status"]
            row["notes"] = row.get("notes") or override["notes"]
            edited += 1
            continue

        if (row.get("suggested_status") or "").strip() == "candidate_approve":
            row["review_status"] = "approved"
            if not row.get("notes"):
                row["notes"] = "Auto-approved from candidate_approve queue."
            approved += 1

    write_rows(path, fieldnames, rows)

    print(f"Approved rows: {approved}")
    print(f"Approved-with-edits rows: {edited}")
    print(f"Updated review sheet: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
