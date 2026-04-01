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
    top = chunks[0] if chunks else {}
    title = (top.get("title") or "Relevant Northeastern KB article").strip()
    url = (top.get("url") or "").strip()
    category = infer_category(question)
    reference_line = f"- {title}: {url}" if url else "None"

    return (
        f"Category: {category}\n"
        "Clarifying question: None\n"
        "Steps:\n"
        "1. I cannot assist with bypassing security controls, obtaining cracked keys, or providing other disallowed instructions.\n"
        "2. Use the approved Northeastern process for legitimate access, enrollment, or account recovery instead.\n"
        "References:\n"
        f"{reference_line}\n"
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
            {
                "question": RunnablePassthrough(),
                "context": RunnableLambda(
                    lambda question: format_retrieved_context(
                        retrieve_kb_chunks(question, top_k=self.top_k)
                    )
                ),
            }
            | prompt
            | self.llm
            | StrOutputParser()
            | RunnableLambda(clean_response)
        )

    def invoke(self, question: str) -> str:
        if is_unsafe_request(question):
            return build_unsafe_response(question, retrieve_kb_chunks(question, top_k=self.top_k))
        return self.chain.invoke(question)
