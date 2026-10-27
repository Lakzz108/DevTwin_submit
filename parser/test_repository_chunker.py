import tempfile
import unittest
from pathlib import Path

from repository_chunker import build_repository_chunks


class RepositoryChunkerTest(unittest.TestCase):
    def test_chunks_python_and_javascript_files_with_repository_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.py").write_text("def login():\n    return True\n", encoding="utf-8")
            (root / "script.js").write_text("function login() {}\n", encoding="utf-8")

            chunks = build_repository_chunks(root, repository_id="repo-1")

        self.assertTrue(chunks)
        self.assertEqual({"api.py", "script.js"}, {chunk["file"] for chunk in chunks})
        self.assertTrue(any(chunk["language"] == "JavaScript" for chunk in chunks))
        self.assertTrue(all(chunk["repository_id"] == "repo-1" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
