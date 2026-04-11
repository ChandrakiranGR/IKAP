import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.app import app


class _StubPipeline:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def invoke_response(self, question: str, history=None) -> dict:
        self.calls.append({"question": question, "history": history or []})
        return self.payload


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint_returns_ok(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_chat_endpoint_returns_answer_and_sources(self) -> None:
        pipeline = _StubPipeline(
            {
                "answer": "Category: VPN access\nClarifying question: None\nSteps:\n1. Install GlobalProtect.\n2. Sign in with your Northeastern account.\nReferences:\n- Install VPN on a Mac: https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0013800\nIf this does not resolve your issue: Contact Northeastern IT Support and include:\n- Your device/OS\n- The step where the issue occurred\n- Any error message shown",
                "mode": "grounded",
                "confidence": "high",
                "structured": {
                    "category": "VPN access",
                    "clarifying_question": None,
                    "steps": ["Install GlobalProtect.", "Sign in with your Northeastern account."],
                    "references": [
                        {
                            "label": "Install VPN on a Mac",
                            "url": "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0013800",
                        }
                    ],
                    "support_message": "If this does not resolve your issue: Contact Northeastern IT Support and include:\n- Your device/OS",
                },
                "chunks": [
                    {
                        "chunk_id": "KB0013800-1",
                        "title": "How do I Install VPN on a Mac?",
                        "kb_id": "KB0013800",
                        "section": "Install VPN on a Mac",
                        "url": "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0013800",
                        "text": "Install GlobalProtect and sign in.",
                    }
                ],
            }
        )

        with patch("backend.api.app.get_pipeline", return_value=pipeline):
            response = self.client.post(
                "/api/chat",
                json={
                    "question": "How do I connect to VPN on my Mac?",
                    "history": [{"role": "user", "content": "I need help with VPN"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["mode"], "grounded")
        self.assertEqual(payload["answer"], pipeline.payload["answer"])
        self.assertEqual(payload["structured"]["category"], "VPN access")
        self.assertEqual(len(payload["sources"]), 1)
        self.assertEqual(
            pipeline.calls,
            [
                {
                    "question": "How do I connect to VPN on my Mac?",
                    "history": [{"role": "user", "content": "I need help with VPN"}],
                }
            ],
        )

    def test_chat_endpoint_skips_source_cards_for_unsupported_mode(self) -> None:
        pipeline = _StubPipeline(
            {
                "answer": "Category: General Northeastern IT support\nClarifying question: What Northeastern IT issue would you like help with?\nSteps:\n1. I can help with Northeastern IT topics.\nReferences:\nNone\nIf this does not resolve your issue: Contact Northeastern IT Support and include:\n- Your device/OS\n- The step where the issue occurred\n- Any error message shown",
                "mode": "unsupported",
                "confidence": "low",
                "structured": {
                    "category": "General Northeastern IT support",
                    "clarifying_question": "What Northeastern IT issue would you like help with?",
                    "steps": ["I can help with Northeastern IT topics."],
                    "references": [],
                    "support_message": "If this does not resolve your issue: Contact Northeastern IT Support and include:\n- Your device/OS",
                },
                "chunks": [],
            }
        )

        with patch("backend.api.app.get_pipeline", return_value=pipeline):
            response = self.client.post("/api/chat", json={"question": "what's the weather?"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "unsupported")
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(payload["sources"], [])

    def test_chat_endpoint_rejects_whitespace_only_questions(self) -> None:
        with patch("backend.api.app.get_pipeline") as get_pipeline_mock:
            response = self.client.post("/api/chat", json={"question": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Question cannot be empty.")
        get_pipeline_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
