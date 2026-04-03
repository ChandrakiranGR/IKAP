import os
from typing import Any, Dict, List
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI

from backend.orchestration.prompt_loader import load_v4_system_prompt
from backend.orchestration.retrieval_adapter import retrieve_kb_chunks


# Keep the stronger base-RAG path as the production default for now.
# The latest fine-tuned checkpoint remains available through IKAP_FINAL_MODEL overrides.
DEFAULT_FINAL_MODEL = "gpt-4o-mini"
LATEST_FINETUNED_MODEL = "ft:gpt-4o-mini-2024-07-18:northeastern-university:ikap-kb-assistant-v2:DPySzTO9"
UNSAFE_QUERY_RE = re.compile(
    r"(?i)\b("
    r"bypass(?:ing)?\s+(?:duo|mfa|multi[- ]factor)|"
    r"disable\s+(?:duo|mfa|multi[- ]factor)|"
    r"internal\s+(?:steps?|process|procedure|workflow)|"
    r"(?:admin|administrator|administrative)\s+(?:steps?|process|procedure|workflow)|"
    r"reset\s+duo\s+for\s+(?:any|another|other)\s+user|"
    r"cracked?\s+(?:license|licence|key)|"
    r"keygen|serial key|pirated?|"
    r"hack(?:ing)?|"
    r"circumvent(?:ing)?\s+(?:security|mfa|duo)"
    r")\b"
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def format_retrieved_context(chunks: List[Dict[str, Any]]) -> str:
    if not chunks:
        return "No KB context retrieved."

    parts = []
    for i, chunk in enumerate(chunks, start=1):
        title = (chunk.get("title") or "").strip()
        url = (chunk.get("url") or "").strip()
        text = (chunk.get("text") or "").strip()
        kb_id = (chunk.get("kb_id") or "").strip()

        parts.append(
            f"[KB Source {i}]\n"
            f"KB ID: {kb_id or 'N/A'}\n"
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


def is_unsafe_request(question: str) -> bool:
    return bool(UNSAFE_QUERY_RE.search(question or ""))


def infer_category(question: str) -> str:
    lowered = (question or "").lower()
    if any(term in lowered for term in ["mfa", "duo", "multi-factor"]):
        return "Multi-Factor Authentication (MFA)"
    if any(term in lowered for term in ["vpn", "globalprotect"]):
        return "VPN access"
    if any(term in lowered for term in ["wifi", "eduroam", "nuwave", "wireless"]):
        return "WiFi and network connectivity"
    if any(term in lowered for term in ["canvas", "turnitin", "qwickly", "respondus"]):
        return "Canvas and teaching tools"
    if any(term in lowered for term in ["matlab", "software", "license", "key"]):
        return "Software access"
    return "Account access"


def build_unsafe_response(question: str, chunks: List[Dict[str, Any]]) -> str:
    category = infer_category(question)

    return (
        f"Category: {category}\n"
        "Clarifying question: None\n"
        "Steps:\n"
        "1. I cannot assist with internal admin procedures, bypassing security controls, or other disallowed instructions.\n"
        "2. Use the approved Northeastern process for legitimate access, enrollment, or account recovery instead.\n"
        "References:\n"
        "None\n"
        "If this does not resolve your issue: Contact Northeastern IT Support and include:\n"
        "- Your device/OS\n"
        "- The step where the issue occurred\n"
        "- Any error message shown"
    )


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
                    "User question:\n{question}\n\n"
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

    def invoke(self, question: str) -> str:
        chunks = retrieve_kb_chunks(question, top_k=self.top_k)
        if is_unsafe_request(question):
            return build_unsafe_response(question, chunks)

        response = self.chain.invoke(
            {
                "question": question,
                "context": format_retrieved_context(chunks),
            }
        )
        notes = _find_supported_scope_notes(question, response, chunks)
        response = _insert_scope_notes(response, notes)
        response = _ensure_link_request_references(question, response, chunks)
        response = _rewrite_explicit_link_request_steps(question, response, chunks)
        response = _ensure_link_request_steps(question, response, chunks)
        return _normalize_link_request_step_urls(question, response)
