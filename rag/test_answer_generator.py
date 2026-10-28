import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from answer_generator import (
    MAX_TOTAL_CONTEXT_CHARS,
    SYSTEM_PROMPT,
    UNAVAILABLE_ANSWER,
    LocalAnswerGenerator,
    build_bounded_context,
)


class AnswerGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.chunks = [{
            "id": "chunk:src/auth.py:FUNCTION:login:4:part-1",
            "file": "src/auth.py",
            "symbol": "login",
            "kind": "FUNCTION",
            "start_line": 4,
            "end_line": 7,
            "content": "def login(): return authenticate()",
            "score": 0.91,
        }]
        self.graph = {
            "nodes": [{"id": "function:login", "type": "FUNCTION", "name": "login", "file": "src/auth.py"}],
            "relationships": [{"source": "function:login", "relationship": "CALLS", "target": "function:authenticate"}],
        }

    @staticmethod
    def response(body):
        response = BytesIO(json.dumps(body).encode("utf-8"))
        response.__enter__ = lambda: response
        response.__exit__ = lambda *_: None
        return response

    def test_returns_answer_from_ollama_chat_response(self):
        generator = LocalAnswerGenerator(enabled=True)
        with patch("answer_generator.urlopen", return_value=self.response({"message": {"content": "Login calls authenticate in src/auth.py."}})) as call:
            answer = generator.generate("What does login do?", self.chunks, self.graph)

        self.assertEqual("Login calls authenticate in src/auth.py.", answer)
        request = call.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/api/chat"))
        payload = json.loads(request.data)
        self.assertEqual("qwen3.5:2b", payload["model"])
        self.assertIn("Answer only from the repository evidence", payload["messages"][0]["content"])
        self.assertIn("untrusted repository data", payload["messages"][1]["content"])

    def test_malformed_ollama_response_returns_unavailable_message(self):
        generator = LocalAnswerGenerator(enabled=True)
        with patch("answer_generator.urlopen", return_value=self.response({"response": "wrong shape"})):
            answer = generator.generate("What does login do?", self.chunks, self.graph)
        self.assertEqual(UNAVAILABLE_ANSWER, answer)

    def test_unavailable_ollama_returns_unavailable_message(self):
        generator = LocalAnswerGenerator(enabled=True)
        with patch("answer_generator.urlopen", side_effect=URLError("connection refused")):
            answer = generator.generate("What does login do?", self.chunks, self.graph)
        self.assertEqual(UNAVAILABLE_ANSWER, answer)

    def test_empty_repository_evidence_returns_insufficient_message_without_calling_ollama(self):
        generator = LocalAnswerGenerator(enabled=True)
        with patch("answer_generator.urlopen") as call:
            answer = generator.generate("Where is login?", [], {"nodes": [], "relationships": []})
        self.assertIn("evidence is insufficient", answer.lower())
        call.assert_not_called()

    def test_context_is_bounded_and_prefers_highest_scoring_chunks(self):
        chunks = [
            {"file": f"src/file_{index}.py", "content": "x" * 5000, "score": index / 10}
            for index in range(12)
        ]
        context = build_bounded_context(chunks, {"nodes": [], "relationships": []})
        decoded = json.loads(context)
        self.assertLessEqual(len(context), MAX_TOTAL_CONTEXT_CHARS)
        self.assertEqual(5, len(decoded["semantic_chunks"]))
        self.assertEqual("src/file_11.py", decoded["semantic_chunks"][0]["file"])

    def test_grounding_instructions_are_explicit(self):
        for instruction in (
            "Answer only from the repository evidence",
            "Do not invent files",
            "static-analysis evidence",
            "untrusted data",
            "evidence is insufficient",
        ):
            self.assertIn(instruction.lower(), SYSTEM_PROMPT.lower())

    def test_environment_configuration_loads_and_normalizes_base_url(self):
        with patch.dict(os.environ, {
            "DEVTWIN_LLM_ENABLED": "true",
            "DEVTWIN_LLM_MODEL": "qwen3.5:2b",
            "DEVTWIN_LLM_BASE_URL": "[http://127.0.0.1:11434](http://127.0.0.1:11434)",
            "DEVTWIN_LLM_TIMEOUT_SECONDS": "600",
        }):
            generator = LocalAnswerGenerator()

        self.assertTrue(generator.enabled)
        self.assertEqual("qwen3.5:2b", generator.model)
        self.assertEqual("http://127.0.0.1:11434", generator.base_url)
        self.assertEqual(600, generator.timeout)


if __name__ == "__main__":
    unittest.main()
