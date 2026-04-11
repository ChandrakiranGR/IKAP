import os
from pathlib import Path
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI

from backend.orchestration.prompt_loader import load_v4_system_prompt
from backend.orchestration.retrieval_adapter import retrieve_kb_chunks
from backend.orchestration.security_constants import INJECTION_PATTERNS

# Keep the stronger base-RAG path as the production default for now.
# The latest fine-tuned checkpoint remains available through IKAP_FINAL_MODEL overrides.
DEFAULT_FINAL_MODEL = "gpt-4o-mini"
LATEST_FINETUNED_MODEL = "ft:gpt-4o-mini-2024-07-18:northeastern-university:ikap-kb-assistant-v2:DPySzTO9"
SUPPORT_FOOTER = (
    "If this does not resolve your issue: Contact Northeastern IT Support and include:\n"
    "- Your device/OS\n"
    "- The step where the issue occurred\n"
    "- Any error message shown"
)
UNSAFE_QUERY_RE = re.compile(
    r"(?i)\b("
    r"bypass(?:ing)?\s+(?:duo|mfa|multi[- ]factor)|"
    r"disable\s+(?:duo|mfa|multi[- ]factor)|"
    r"internal\s+(?:steps?|process|procedure|workflow)|"
    r"(?:admin|administrator|administrative)(?:-only)?[\s-]+(?:steps?|process|procedure|workflow|information)|"
    r"reset\s+duo\s+for\s+(?:any|another|other)\s+user|"
    r"cracked?\s+(?:license|licence|key)|"
    r"keygen|serial key|pirated?|"
    r"hack(?:ing)?|"
    r"circumvent(?:ing)?\s+(?:security|mfa|duo)"
    r")\b"
)
SECRET_QUERY_RE = re.compile(
    r"(?i)\b("
    r"api\s*key|access\s*token|secret\s*key|private\s*key|credentials?|passwords?|"
    r"env(?:ironment)?\s*file|\.env|backend\s+key|openai\s+key"
    r")\b"
)
PRIVACY_QUERY_RE = re.compile(
    r"(?i)\b(?:provide|give|share|tell|what(?:'s| is)|find)\b.*\b("
    r"email|e-mail|email address|phone(?: number)?|contact(?: info| information)?|address"
    r")\b"
)
OUT_OF_SCOPE_QUERY_RE = re.compile(
    r"(?i)\b("
    r"weather|forecast|temperature|rain|snow|boston weather|news|restaurant|movie|recipe|"
    r"capital of|stock price|sports score|horoscope|joke|poem|translate"
    r")\b"
)
GREETING_QUERY_RE = re.compile(
    r"(?i)^\s*(hi|hello|hey|help|good\s+(?:morning|afternoon|evening))\b"
)
FOLLOW_UP_QUERY_RE = re.compile(
    r"(?i)\b("
    r"windows|mac|macos|android|iphone|ios|chromebook|linux|faculty|student|staff|"
    r"it|that|this|same|different|still|now|again|authentication failed|error|not working|"
    r"before i publish|before publishing|new phone"
    r")\b"
)
IT_SCOPE_TERMS = {
    "account",
    "canvas",
    "duo",
    "eduroam",
    "email",
    "mfa",
    "northeastern",
    "nuwave",
    "password",
    "qwickly",
    "respondus",
    "software",
    "student hub",
    "studenthub",
    "turnitin",
    "touch id",
    "vpn",
    "wifi",
}
AMBIGUOUS_SHORT_TERMS = {
    "windows",
    "mac",
    "android",
    "iphone",
    "ios",
    "faculty",
    "student",
    "staff",
    "help",
}

def detect_injection(question: str) -> bool:
    """
    Checks user input for injection-style attack patterns.
    Returns True if any pattern is found.
    This runs BEFORE retrieval so the KB index is never queried
    for known attack inputs.
    """
    lowered = (question or "").lower()
    return any(pattern in lowered for pattern in INJECTION_PATTERNS)


def is_unsafe_request(question: str) -> bool:
    """
    Combined check: operational unsafe patterns OR injection patterns.
    """
    return bool(UNSAFE_QUERY_RE.search(question or "")) or detect_injection(question)

def validate_input(question: str) -> tuple[bool, str]:
    if not question or not question.strip():
        return False, "empty"
    stripped = question.strip()
        
    if len(stripped) > 2000:
        return False, "too_long"
    return True, ""

def build_validation_response(reason: str, question: str) -> str:
    category = infer_category(question)
    if reason == "empty":
        step = "1. Please enter a valid IT support question."
    elif reason == "malformed":
        step = "1. The input could not be understood. Please enter a clear IT support question."
    else:
        step = "1. The input is too long. Please summarize your question and try again."
    return (
        f"Category: {category}\n"
        "Clarifying question: None\n"
        f"Steps:\n{step}\n"
        "References:\nNone\n"
        "If this does not resolve your issue: Contact Northeastern IT Support and include:\n"
        "- Your device/OS\n"
        "- The step where the issue occurred\n"
        "- Any error message shown"
    )

def build_injection_response(question: str) -> str:
    """
    Returns a formatted refusal specifically for injection attempts.
    Distinct from build_unsafe_response so the report can show
    different handling for different attack types.
    """
    category = infer_category(question)
    return (
        f"Category: {category}\n"
        "Clarifying question: None\n"
        "Steps:\n"
        "1. This request appears to contain instructions that attempt to modify "
        "IKAP's behavior or access restricted information. IKAP cannot process it.\n"
        "2. If you have a genuine IT support question, please rephrase and ask again.\n"
        "References:\n"
        "None\n"
        "If this does not resolve your issue: Contact Northeastern IT Support and include:\n"
        "- Your device/OS\n"
        "- The step where the issue occurred\n"
        "- Any error message shown"
    )

def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_history(history: List[Dict[str, str]] | None) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized[-6:]


def _contains_it_scope_signal(text: str) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in IT_SCOPE_TERMS)


def _tokenize_words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _looks_like_nonsense(question: str) -> bool:
    lowered = re.sub(r"[^a-z]", "", (question or "").lower())
    tokens = _tokenize_words(question)
    if not lowered or _contains_it_scope_signal(question):
        return False
    if len(tokens) <= 2 and len(lowered) >= 12 and len(set(lowered)) <= 4:
        return True
    if len(tokens) == 1 and len(tokens[0]) >= 10 and len(set(tokens[0])) <= 3:
        return True
    return False


def _is_privacy_request(question: str) -> bool:
    lowered = (question or "").lower()
    if not PRIVACY_QUERY_RE.search(lowered):
        return False
    if any(term in lowered for term in ["my email", "my phone", "my address", "my contact"]):
        return False
    return any(
        term in lowered
        for term in [
            "someone else",
            "another person",
            "another user",
            "other user",
            "their email",
            "'s northeastern email",
            "northeastern email address",
        ]
    )


def _is_secret_request(question: str) -> bool:
    lowered = (question or "").lower()
    return bool(SECRET_QUERY_RE.search(lowered)) and any(
        term in lowered for term in ["ikap", "backend", "openai", "api", "credential", "secret"]
    )


def _is_out_of_scope(question: str) -> bool:
    lowered = (question or "").lower()
    return bool(OUT_OF_SCOPE_QUERY_RE.search(lowered)) and not _contains_it_scope_signal(lowered)


def _looks_like_greeting(question: str) -> bool:
    lowered = (question or "").strip().lower()
    return bool(GREETING_QUERY_RE.match(lowered)) and not _contains_it_scope_signal(lowered)


def _is_context_dependent_follow_up(question: str) -> bool:
    lowered = (question or "").strip().lower()
    tokens = _tokenize_words(lowered)
    if not lowered:
        return False
    if lowered in AMBIGUOUS_SHORT_TERMS:
        return True
    if len(tokens) <= 8 and FOLLOW_UP_QUERY_RE.search(lowered):
        return True
    if len(tokens) <= 4 and not _contains_it_scope_signal(lowered):
        return True
    return False


def _is_self_contained_question(question: str) -> bool:
    lowered = (question or "").strip().lower()
    tokens = _tokenize_words(lowered)
    if not lowered:
        return False
    if _is_out_of_scope(lowered) or _looks_like_nonsense(lowered) or _is_privacy_request(lowered):
        return True
    if _contains_it_scope_signal(lowered) and len(tokens) >= 4 and not _is_context_dependent_follow_up(lowered):
        return True
    return lowered.endswith("?") and len(tokens) >= 6 and not _is_context_dependent_follow_up(lowered)


def build_effective_question(question: str, history: List[Dict[str, str]] | None = None) -> str:
    current = (question or "").strip()
    normalized_history = _normalize_history(history)
    if not current or not normalized_history or _is_self_contained_question(current):
        return current

    prior_user_turns = [
        item["content"].strip()
        for item in normalized_history
        if item["role"] == "user" and item["content"].strip()
    ]
    if not prior_user_turns:
        return current

    seed_turns: List[str] = []
    for prior in reversed(prior_user_turns):
        if prior.lower() == current.lower():
            continue
        seed_turns.insert(0, prior)
        if _contains_it_scope_signal(prior):
            break
        if len(seed_turns) >= 2:
            break

    if not seed_turns:
        return current

    if _is_context_dependent_follow_up(current):
        return f"Original issue: {' '.join(seed_turns)} Follow-up detail: {current}".strip()

    return current


def infer_category(question: str) -> str:
    lowered = (question or "").lower()
    if any(term in lowered for term in ["mfa", "duo", "multi-factor", "touch id"]):
        return "Multi-Factor Authentication (MFA)"
    if any(term in lowered for term in ["vpn", "globalprotect"]):
        return "VPN access"
    if any(term in lowered for term in ["wifi", "eduroam", "nuwave", "wireless"]):
        return "WiFi and network connectivity"
    if any(term in lowered for term in ["canvas", "turnitin", "qwickly", "respondus"]):
        return "Canvas and teaching tools"
    if any(term in lowered for term in ["matlab", "software", "license", "mathematica", "labview"]):
        return "Software access"
    return "Account access"


def classify_request(question: str, history: List[Dict[str, str]] | None = None) -> Dict[str, str]:
    current = (question or "").strip()
    effective_question = build_effective_question(current, history)

    if _is_secret_request(current) or is_unsafe_request(current):
        return {"route": "unsafe", "reason": "unsafe", "effective_question": effective_question}
    if _is_privacy_request(current):
        return {"route": "unsafe", "reason": "privacy", "effective_question": effective_question}
    if _looks_like_nonsense(current):
        return {"route": "unsupported", "reason": "nonsense", "effective_question": effective_question}
    if _is_out_of_scope(current):
        return {"route": "unsupported", "reason": "unsupported", "effective_question": effective_question}
    if _looks_like_greeting(current):
        return {"route": "clarify", "reason": "greeting", "effective_question": effective_question}
    if not _contains_it_scope_signal(effective_question) and _is_context_dependent_follow_up(current):
        return {"route": "clarify", "reason": "ambiguous", "effective_question": effective_question}
    return {"route": "grounded", "reason": "grounded", "effective_question": effective_question}


def format_recent_history(history: List[Dict[str, str]] | None) -> str:
    normalized_history = _normalize_history(history)
    if not normalized_history:
        return "None"
    return "\n".join(
        f"{item['role'].capitalize()}: {item['content']}" for item in normalized_history
    )


def format_retrieved_context(chunks: List[Dict[str, Any]]) -> str:
    if not chunks:
        return "No KB context retrieved."

    parts = []
    for i, chunk in enumerate(chunks, start=1):
        title = (chunk.get("title") or "").strip()
        url = (chunk.get("url") or "").strip()
        text = (chunk.get("text") or "").strip()
        kb_id = (chunk.get("kb_id") or "").strip()
        score = float(chunk.get("score") or 0.0)

        parts.append(
            f"[KB Source {i}]\n"
            f"KB ID: {kb_id or 'N/A'}\n"
            f"Score: {score:.4f}\n"
            f"Title: {title or 'Untitled'}\n"
            f"Direct Link: {url or 'N/A'}\n"
            f"Content:\n{text or 'None'}\n"
        )

    return "\n".join(parts)


def clean_response(text: str) -> str:
    text = text.strip()

    text = text.replace(
        "Steps (KB-grounded if context is provided; otherwise general guidance):",
        "Steps:",
    )

    text = re.sub(r"Steps\s*\(.*?\):", "Steps:", text, flags=re.IGNORECASE)

    text = text.replace(
        'References (only if provided in KB context/links; otherwise "None"):',
        "References:",
    )
    text = re.sub(r"References\s*\(.*?\):", "References:", text, flags=re.IGNORECASE)

    text = text.replace("page .", "page.")
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _find_supported_scope_notes(question: str, response: str, chunks: List[Dict[str, Any]]) -> List[str]:
    question_l = (question or "").lower()
    response_l = (response or "").lower()
    combined_context = " ".join(
        " ".join(
            [
                (chunk.get("title") or "").lower(),
                (chunk.get("text") or "").lower(),
            ]
        )
        for chunk in chunks[:2]
    )

    notes: List[str] = []
    platform_labels = [
        ("mac", "Scope: Mac."),
        ("macos", "Scope: macOS."),
        ("windows", "Scope: Windows."),
        ("android", "Scope: Android."),
        ("iphone", "Scope: iPhone."),
        ("ios", "Scope: iOS."),
        ("chromebook", "Scope: Chromebook."),
        ("linux", "Scope: Linux."),
    ]
    for term, note in platform_labels:
        if term in question_l and term not in response_l and term in combined_context:
            notes.append(note)
            break

    audience_labels = [
        ("faculty", "Audience: Faculty."),
        ("student", "Audience: Student."),
        ("staff", "Audience: Staff."),
    ]
    for term, note in audience_labels:
        if term in question_l and term not in response_l and term in combined_context:
            notes.append(note)
            break

    if (
        any(term in question_l for term in ["publish", "published", "unpublished", "before publishing", "before i publish"])
        and "publish" not in response_l
        and any(term in combined_context for term in ["publish", "published", "unpublished"])
    ):
        notes.append("Timing: This guidance applies before the course is published when the KB says Qwickly works with unpublished courses.")

    return notes


def _insert_scope_notes(response: str, notes: List[str]) -> str:
    if not notes:
        return response

    marker = "Clarifying question: None\n"
    note_block = "\n".join(notes) + "\n"
    if marker in response:
        return response.replace(marker, marker + note_block, 1)
    return note_block + response


def _is_link_request(question: str) -> bool:
    question_l = (question or "").lower()
    explicit_phrases = [
        "give me the link",
        "send me the link",
        "what is the link",
        "article link",
        "url",
        "link to",
    ]
    if any(phrase in question_l for phrase in explicit_phrases):
        return True

    request_terms = ["give", "send", "share", "what", "need", "provide"]
    return "link" in question_l and any(term in question_l for term in request_terms)


def _is_explicit_link_request(question: str) -> bool:
    question_l = (question or "").lower()
    return any(
        phrase in question_l
        for phrase in [
            "give me the link",
            "send me the link",
            "what is the link",
            "give me the",
            "send me the",
        ]
    )


def _count_numbered_steps(response: str) -> int:
    return len(re.findall(r"(?m)^\d+\.\s+", response or ""))


def _ensure_link_request_steps(question: str, response: str, chunks: List[Dict[str, Any]]) -> str:
    if not _is_link_request(question) or _count_numbered_steps(response) >= 2:
        return response

    title = (chunks[0].get("title") or "the KB article") if chunks else "the KB article"
    extra_step = f"2. Open the KB article in References and follow the detailed steps in {title}."

    marker = "\nReferences:\n"
    if marker in response:
        return response.replace(marker, f"\n{extra_step}{marker}", 1)
    return response + f"\n{extra_step}"


def _ensure_link_request_references(question: str, response: str, chunks: List[Dict[str, Any]]) -> str:
    if not _is_link_request(question):
        return response

    title = ""
    url = ""
    for chunk in chunks:
        title = (chunk.get("title") or "").strip()
        url = (chunk.get("url") or "").strip()
        if title and url:
            break

    if not title or not url:
        return response

    reference_block = f"References:\n- {title}: {url}\n"
    footer_match = re.search(r"(?m)^If this does not resolve your issue:", response)
    references_match = re.search(r"(?m)^References:.*$", response)

    if references_match:
        start = references_match.start()
        end = footer_match.start() if footer_match else len(response)
        prefix = response[:start]
        suffix = response[end:]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        return prefix + reference_block + suffix.lstrip("\n")

    if footer_match:
        start = footer_match.start()
        prefix = response[:start]
        suffix = response[start:]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        return prefix + reference_block + suffix

    if response and not response.endswith("\n"):
        response += "\n"
    return response + reference_block


def _normalize_link_request_step_urls(question: str, response: str) -> str:
    if not _is_link_request(question):
        return response

    normalized_lines = []
    for line in response.splitlines():
        if re.match(r"^\d+\.\s+", line) and "http" in line:
            line = re.sub(r"https?://\S+", "the KB article listed in References", line)
            line = line.replace(
                "visit the following link: the KB article listed in References",
                "open the KB article listed in References",
            )
            line = line.replace(
                "visit the following link the KB article listed in References",
                "open the KB article listed in References",
            )
            line = line.replace(
                ": the KB article listed in References.",
                " the KB article listed in References.",
            )
            line = line.replace(
                "the following link the KB article listed in References",
                "the KB article listed in References",
            )
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _rewrite_explicit_link_request_steps(
    question: str,
    response: str,
    chunks: List[Dict[str, Any]],
) -> str:
    if not _is_explicit_link_request(question):
        return response

    steps_marker = "Steps:\n"
    if steps_marker not in response:
        return response

    references_match = re.search(r"(?m)^References:.*$", response)
    if not references_match:
        return response

    title = (chunks[0].get("title") or "the relevant KB article").strip() if chunks else "the relevant KB article"
    question_l = (question or "").lower()

    descriptor = "the KB article"
    if "faculty" in question_l or "faculty" in title.lower():
        descriptor = "the faculty KB article"
    elif "student" in question_l or "student" in title.lower():
        descriptor = "the student KB article"

    if "duo" in question_l and "new phone" in question_l:
        replacement = (
            "Steps:\n"
            f"1. Open {descriptor} listed in References.\n"
            "2. If you kept the same phone number, sign in from a computer, use 'Call Me' to authenticate, and choose 'Reactivate Duo Mobile' for your registered number.\n"
            "3. If your phone number changed, sign in to the Northeastern MFA website, delete the old device, and add your new device.\n"
            "4. If your new phone cannot receive calls or you cannot complete the update, contact the IT Service Desk.\n"
        )
    elif "password" in question_l and "reset" in question_l:
        replacement = (
            "Steps:\n"
            f"1. Open {descriptor} listed in References.\n"
            "2. Enter your Northeastern username, choose the email address to receive the reset message, and send the password reset email.\n"
            "3. Open the reset link from that email, complete MFA if prompted, and save your new password.\n"
        )
    else:
        step_two = f"2. Follow the detailed instructions in {title} for the exact steps and requirements."
        replacement = (
            "Steps:\n"
            f"1. Open {descriptor} listed in References.\n"
            f"{step_two}\n"
        )

    start = response.index(steps_marker)
    end = references_match.start()
    return response[:start] + replacement + response[end:]

def _split_reference_line(line: str) -> Dict[str, str] | None:
    cleaned = line.strip().lstrip("-").strip()
    if not cleaned or cleaned.lower() == "none":
        return None

    match = re.search(r"https?://\S+", cleaned)
    if not match:
        return None
    url = match.group(0).rstrip(").,;]>")
    label = cleaned[: match.start()].rstrip(": ").strip() or "KB article"
    return {"label": label, "url": url}


def parse_structured_answer(answer: str) -> Dict[str, Any]:
    category = None
    clarifying_question = None
    steps: List[str] = []
    references: List[Dict[str, str]] = []
    support_lines: List[str] = []
    state = ""

    for raw_line in (answer or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("Category:"):
            value = line.split(":", 1)[1].strip()
            category = value or None
            state = ""
            continue
        if line.startswith("Clarifying question:"):
            value = line.split(":", 1)[1].strip()
            clarifying_question = None if value.lower() == "none" else value
            state = ""
            continue
        if line.startswith("Steps:"):
            state = "steps"
            continue
        if line.startswith("References:"):
            state = "references"
            inline = line.split(":", 1)[1].strip()
            ref = _split_reference_line(inline) if inline else None
            if ref:
                references.append(ref)
            continue
        if line.startswith("If this does not resolve your issue:"):
            state = "support"
            support_lines = [line]
            continue

        if state == "steps" and re.match(r"^\d+\.\s+", line):
            steps.append(re.sub(r"^\d+\.\s+", "", line).strip())
            continue

        if state == "references":
            ref = _split_reference_line(line)
            if ref:
                references.append(ref)
            continue

        if state == "support":
            support_lines.append(line)

    return {
        "category": category,
        "clarifying_question": clarifying_question,
        "steps": steps,
        "references": references,
        "support_message": "\n".join(support_lines) if support_lines else SUPPORT_FOOTER,
    }


def _fallback_references_from_chunks(chunks: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, str]]:
    references: List[Dict[str, str]] = []
    seen = set()
    for chunk in chunks:
        title = (chunk.get("title") or "").strip()
        url = (chunk.get("url") or "").strip()
        if not title or not url or url in seen:
            continue
        seen.add(url)
        references.append({"label": title, "url": url})
        if len(references) >= limit:
            break
    return references


def _render_answer(structured: Dict[str, Any]) -> str:
    category = structured.get("category") or "General Northeastern IT support"
    clarifying_question = structured.get("clarifying_question") or "None"
    steps = structured.get("steps") or []
    references = structured.get("references") or []
    support_message = structured.get("support_message") or SUPPORT_FOOTER

    parts = [f"Category: {category}", f"Clarifying question: {clarifying_question}", "Steps:"]
    if steps:
        parts.extend(f"{idx}. {step}" for idx, step in enumerate(steps, start=1))
    else:
        parts.append("1. Please restate the Northeastern IT issue you need help with.")

    parts.append("References:")
    if references:
        parts.extend(f"- {ref['label']}: {ref['url']}" for ref in references if ref.get("url"))
    else:
        parts.append("None")

    parts.append(support_message)
    return "\n".join(parts)


def _build_structured_response(
    *,
    category: str,
    clarifying_question: str | None,
    steps: List[str],
    references: List[Dict[str, str]] | None = None,
    support_message: str | None = None,
) -> Dict[str, Any]:
    structured = {
        "category": category,
        "clarifying_question": clarifying_question,
        "steps": steps,
        "references": references or [],
        "support_message": support_message or SUPPORT_FOOTER,
    }
    return {
        "answer": _render_answer(structured),
        "structured": structured,
    }


def build_clarify_response(question: str) -> Dict[str, Any]:
    category = infer_category(question) if _contains_it_scope_signal(question) else "General Northeastern IT support"
    return _build_structured_response(
        category=category,
        clarifying_question="What Northeastern IT issue do you need help with?",
        steps=[
            "Tell me the specific Northeastern IT service or problem, such as password reset, Duo MFA, VPN, Wi-Fi, Canvas, software, or Student Hub.",
            "If you are troubleshooting, include your device or platform and the exact error message you saw.",
            "Example: 'I cannot connect to VPN on my Windows laptop and it says authentication failed.'",
        ],
    )


def build_unsupported_response(question: str, reason: str = "unsupported") -> Dict[str, Any]:
    first_step = (
        "I can help with Northeastern IT topics such as passwords, Duo MFA, VPN, Wi-Fi, Canvas, software, and Student Hub."
    )
    if reason == "nonsense":
        first_step = (
            "I could not understand that request well enough to match it to a Northeastern IT help topic."
        )

    return _build_structured_response(
        category="General Northeastern IT support",
        clarifying_question="What Northeastern IT issue would you like help with?",
        steps=[
            first_step,
            "Please rephrase your question with the specific Northeastern IT task, service, or error you want help with.",
            "Example questions: 'How do I reset my Northeastern password?' or 'How do I connect to VPN on Windows?'",
        ],
    )


def build_unsafe_response(question: str, chunks: List[Dict[str, Any]], reason: str = "unsafe") -> str:
    return _build_unsafe_payload(question, reason)["answer"]


def _build_unsafe_payload(question: str, reason: str) -> Dict[str, Any]:
    category = "Security and privacy"
    if reason == "privacy":
        steps = [
            "I cannot provide another person's Northeastern email address or contact details.",
            "Use approved university directories or official contact channels if you have a legitimate need to reach that person.",
            "If you need help with your own Northeastern account or contact information, tell me that specific IT issue and I can help.",
        ]
    else:
        steps = [
            "I cannot assist with internal admin procedures, bypassing security controls, or other disallowed instructions.",
            "I also cannot provide API keys, credentials, or other secrets.",
            "Use the approved Northeastern process for legitimate access, enrollment, or account recovery instead.",
            "If you believe you should have authorized access, contact the system owner or Northeastern IT Support through the normal channel.",
        ]

    return _build_structured_response(
        category=category,
        clarifying_question=None,
        steps=steps,
    )
def _lexical_overlap_count(question: str, chunk: Dict[str, Any]) -> int:
    q_tokens = {
        token
        for token in _tokenize_words(question)
        if token not in {"how", "what", "when", "where", "why", "the", "and", "for", "with", "my", "on", "to"}
    }
    chunk_tokens = set(_tokenize_words(f"{chunk.get('title', '')} {chunk.get('text', '')}"))
    return len(q_tokens & chunk_tokens)


def _is_weak_retrieval(question: str, chunks: List[Dict[str, Any]]) -> str | None:
    if not chunks:
        return "unsupported"

    top_score = float(chunks[0].get("score") or 0.0)
    second_score = float(chunks[1].get("score") or 0.0) if len(chunks) > 1 else 0.0
    overlap = _lexical_overlap_count(question, chunks[0])
    combined = f"{chunks[0].get('title', '')} {chunks[0].get('text', '')}".lower()

    if "admin access" in question.lower() and "admin" not in combined:
        return "clarify"
    if top_score < 0.45 and overlap < 2:
        return "unsupported"
    if top_score < 0.62:
        return "clarify"
    if second_score and (top_score - second_score) < 0.03 and overlap < 3:
        return "clarify"
    return None


def infer_confidence(mode: str, chunks: List[Dict[str, Any]], question: str) -> str:
    if mode != "grounded" or not chunks:
        return "low"

    top_score = float(chunks[0].get("score") or 0.0)
    overlap = _lexical_overlap_count(question, chunks[0])
    has_reference = bool((chunks[0].get("url") or "").strip())

    if top_score >= 0.8 and overlap >= 2 and has_reference:
        return "high"
    if top_score >= 0.62 and overlap >= 1:
        return "medium"
    return "low"


class IKAPLangChainPipeline:
    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.3,
        top_k: int = 1,
    ):
        load_dotenv(_project_root() / ".env")

        self.model_name = model_name or os.getenv("IKAP_FINAL_MODEL") or DEFAULT_FINAL_MODEL
        self.temperature = temperature
        self.top_k = top_k
        self.system_prompt = load_v4_system_prompt()

        self.llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
        )

        self.chain = self._build_chain()

    def _build_chain(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    self.system_prompt
                    + "\n\n"
                    + "Use retrieved KB context when relevant. "
                    + "Do not invent citations or links. "
                    + "If the user explicitly asks for a link and a relevant KB URL is present in retrieved context, include that URL. "
                    + "If a relevant KB URL is not present in retrieved context, do not make one up. "
                    + "If the user explicitly asks for a link, place the URL under 'References:' and do not leave References as 'None'. "
                    + "Avoid putting a raw URL only inside a numbered step unless the KB context makes clicking that URL an explicit step. "
                    + "If the user asks for a link, still include the surrounding KB-grounded steps or decision points needed to use that link; do not reduce the answer to only a single link step. "
                    + "Use the heading 'Steps:' only. "
                    + "Use the heading 'References:' only. "
                    + "Prioritize correctness and completeness over brevity. "
                    + "Provide the right information from the KB even if multiple details are needed. "
                    + "Convert noisy KB prose into clear user-facing instructions without losing important meaning. "
                    + "Keep all necessary steps required to complete the task. "
                    + "Preserve important notes or conditions when they are relevant to successfully completing the task. "
                    + "Do not include partial or broken sentences. "
                    + "If the KB content is noisy, extract the most reliable actionable guidance and present it clearly. "
                    + "For configuration or setup questions, preserve exact KB-backed values such as EAP method, certificate settings, identity fields, domains, portal addresses, and version-specific branches whenever they appear in retrieved context. "
                    + "Do not compress configuration-heavy KBs into overly short summaries when the source contains exact required values or option branches. "
                    + "When the question specifies a platform or device such as Android, iPhone, iOS, Windows, Mac, macOS, Chromebook, or Linux, keep that platform explicit in the response instead of generalizing it away. "
                    + "When the question includes a timing, platform, or scope qualifier such as 'before the course is published', 'on your Mac', or 'with a new phone', repeat that qualifier explicitly in the response when the KB context supports it. "
                    + "If the user asks for unsafe or disallowed instructions, Step 1 must explicitly say that you cannot assist or cannot provide those instructions before offering safe alternatives. "
                    + "Keep the response aligned with the IKAP format.",
                ),
                (
                    "human",
                    "Current user question:\n{question}\n\n"
                    "Recent conversation history:\n{history}\n\n"
                    "Effective retrieval question:\n{effective_question}\n\n"
                    "Retrieved KB context:\n{context}\n\n"
                    "If the user is explicitly asking for a link, prioritize returning the most relevant KB link from the retrieved context.",
                ),
            ]
        )

        return (
            RunnablePassthrough()
            | prompt
            | self.llm
            | StrOutputParser()
            | RunnableLambda(clean_response)
        )

    def invoke_response(
        self,
        question: str,
        history: List[Dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        is_valid, validation_reason = validate_input(question)
        if not is_valid:
            answer = build_validation_response(validation_reason, question)
            structured = parse_structured_answer(answer)
            return {
                "answer": answer,
                "mode": "clarify",
                "structured": structured,
                "confidence": "low",
                "chunks": [],
                "effective_question": question.strip(),
            }

        if detect_injection(question):
            answer = build_injection_response(question)
            structured = parse_structured_answer(answer)
            return {
                "answer": answer,
                "mode": "unsafe",
                "structured": structured,
                "confidence": "low",
                "chunks": [],
                "effective_question": question.strip(),
            }

        normalized_history = _normalize_history(history)
        classification = classify_request(question, normalized_history)
        effective_question = classification["effective_question"]
        route = classification["route"]
        reason = classification["reason"]

        if route == "unsafe":
            payload = _build_unsafe_payload(question, reason)
            return {
                "answer": payload["answer"],
                "mode": "unsafe",
                "structured": payload["structured"],
                "confidence": "low",
                "chunks": [],
                "effective_question": effective_question,
            }

        if route == "unsupported":
            payload = build_unsupported_response(question, reason)
            return {
                "answer": payload["answer"],
                "mode": "unsupported",
                "structured": payload["structured"],
                "confidence": "low",
                "chunks": [],
                "effective_question": effective_question,
            }

        if route == "clarify":
            payload = build_clarify_response(question)
            return {
                "answer": payload["answer"],
                "mode": "clarify",
                "structured": payload["structured"],
                "confidence": "low",
                "chunks": [],
                "effective_question": effective_question,
            }

        chunks = retrieve_kb_chunks(effective_question, top_k=self.top_k)
        weak_mode = _is_weak_retrieval(effective_question, chunks)
        if weak_mode == "unsupported":
            payload = build_unsupported_response(question, "unsupported")
            return {
                "answer": payload["answer"],
                "mode": "unsupported",
                "structured": payload["structured"],
                "confidence": "low",
                "chunks": [],
                "effective_question": effective_question,
            }
        if weak_mode == "clarify":
            payload = build_clarify_response(question)
            return {
                "answer": payload["answer"],
                "mode": "clarify",
                "structured": payload["structured"],
                "confidence": "low",
                "chunks": [],
                "effective_question": effective_question,
            }

        response = self.chain.invoke(
            {
                "question": question,
                "history": format_recent_history(normalized_history),
                "effective_question": effective_question,
                "context": format_retrieved_context(chunks),
            }
        )
        notes = _find_supported_scope_notes(question, response, chunks)
        response = _insert_scope_notes(response, notes)
        response = _ensure_link_request_references(question, response, chunks)
        response = _rewrite_explicit_link_request_steps(question, response, chunks)
        response = _ensure_link_request_steps(question, response, chunks)
        response = _normalize_link_request_step_urls(question, response)

        structured = parse_structured_answer(response)
        if not structured.get("category"):
            structured["category"] = infer_category(question)
        if not structured.get("references"):
            structured["references"] = _fallback_references_from_chunks(chunks)
            response = _render_answer(structured)

        return {
            "answer": response,
            "mode": "grounded",
            "structured": structured,
            "confidence": infer_confidence("grounded", chunks, effective_question),
            "chunks": chunks,
            "effective_question": effective_question,
        }

    def invoke(self, question: str) -> str:
        return self.invoke_response(question)["answer"]
