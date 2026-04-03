import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.app import app


class _StubPipeline:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.questions: list[str] = []

    def invoke(self, question: str) -> str:
        self.questions.append(question)
        return self.answer


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint_returns_ok(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_chat_endpoint_returns_answer_and_sources(self) -> None:
        pipeline = _StubPipeline(
            "Category: VPN access\n"
            "Clarifying question: None\n"
            "Steps:\n"
            "1. Install GlobalProtect.\n"
            "2. Sign in with your Northeastern account.\n"
            "References:\n"
            "- Install VPN on a Mac: https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0013800\n"
            "If this does not resolve your issue: Contact Northeastern IT Support and include:\n"
            "- Your device/OS\n"
            "- The step where the issue occurred\n"
            "- Any error message shown"
        )
        sources = [
            {
                "chunk_id": "KB0013800-1",
                "article_title": "How do I Install VPN on a Mac?",
                "article_id": "KB0013800",
                "section": "Install VPN on a Mac",
                "source_url": "https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article=KB0013800",
                "snippet": "Install GlobalProtect and sign in.",
            }
        ]

        with patch("backend.api.app.get_pipeline", return_value=pipeline), patch(
            "backend.api.app.build_sources", return_value=sources
        ):
            response = self.client.post(
                "/api/chat",
                json={"question": "How do I connect to VPN on my Mac?"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["confidence"], "medium")
        self.assertEqual(payload["answer"], pipeline.answer)
        self.assertEqual(payload["sources"], sources)
        self.assertEqual(pipeline.questions, ["How do I connect to VPN on my Mac?"])

    def test_chat_endpoint_rejects_whitespace_only_questions(self) -> None:
        with patch("backend.api.app.get_pipeline") as get_pipeline_mock:
            response = self.client.post("/api/chat", json={"question": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Question cannot be empty.")
        get_pipeline_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
