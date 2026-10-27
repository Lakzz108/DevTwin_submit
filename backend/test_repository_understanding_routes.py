import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class RepositoryUnderstandingRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def test_github_route_clones_url_then_runs_repository_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch.object(main, "fetch_public_repository", return_value=(Path(temporary_directory), "octocat/hello")) as fetch,
                patch.object(main, "_ingest_repository", return_value={
                    "repository_id": "repo-1", "repository_path": temporary_directory,
                    "project_understanding": {}, "files_analyzed": 1,
                }) as ingest,
            ):
                response = self.client.post(
                    "/repositories/github",
                    json={"url": "https://github.com/octocat/hello"},
                )

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("octocat/hello", response.json()["repository_name"])
        self.assertEqual("github", response.json()["source"])
        fetch.assert_called_once_with("https://github.com/octocat/hello")
        self.assertEqual(Path(temporary_directory), ingest.call_args.args[0])

    def test_invalid_github_url_is_a_clean_client_error(self):
        response = self.client.post(
            "/repositories/github",
            json={"url": "https://example.com/not-a-github-repository"},
        )

        self.assertEqual(422, response.status_code)
        self.assertIn("public GitHub URL", response.json()["detail"])
        self.assertNotIn("Traceback", response.text)

    def test_github_clone_failure_is_clean_and_does_not_return_git_output(self):
        with patch.object(main, "fetch_public_repository", side_effect=main.GitHubRepositoryError("DevTwin could not clone this repository. Check that the URL is a public GitHub repository and try again.")):
            response = self.client.post(
                "/repositories/github",
                json={"url": "https://github.com/private/missing"},
            )

        self.assertEqual(400, response.status_code)
        self.assertIn("could not clone", response.json()["detail"])
        self.assertNotIn("Traceback", response.text)

    def test_file_summary_uses_docstring_and_extracted_facts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                '"""Checks submitted user credentials."""\n\n'
                "def authenticate(user):\n    return user\n",
                encoding="utf-8",
            )
            response = self.client.post(
                "/repositories/file-summary",
                json={"repository_path": temporary_directory, "file": "service.py"},
            )

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("Python", response.json()["language"])
        self.assertIn("submitted user credentials", response.json()["purpose"])
        self.assertEqual(["authenticate"], response.json()["functions"])


if __name__ == "__main__":
    unittest.main()
