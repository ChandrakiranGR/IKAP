from typing import Any, Dict, List
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI

from backend.orchestration.prompt_loader import load_v4_system_prompt
from backend.orchestration.retrieval_adapter import retrieve_kb_chunks


FINAL_MODEL = "ft:gpt-4o-mini-2024-07-18:northeastern-university::DHXUyO6e"


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

    text = text.replace("page .", "page.")
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class IKAPLangChainPipeline:
    def __init__(
        self,
        model_name: str = FINAL_MODEL,
        temperature: float = 0.3,
        top_k: int = 1,
    ):
        self.model_name = model_name
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
                    + "Use the heading 'Steps:' only. "
                    + "Use the heading 'References:' only. "
                    + "Prioritize correctness and completeness over brevity. "
                    + "Provide the right information from the KB even if multiple details are needed. "
                    + "Convert noisy KB prose into clear user-facing instructions without losing important meaning. "
                    + "Keep all necessary steps required to complete the task. "
                    + "Preserve important notes or conditions when they are relevant to successfully completing the task. "
                    + "Do not include partial or broken sentences. "
                    + "If the KB content is noisy, extract the most reliable actionable guidance and present it clearly. "
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
        return self.chain.invoke(question)
