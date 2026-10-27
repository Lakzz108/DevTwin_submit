import tempfile
import unittest
from pathlib import Path

from repository_understanding import build_project_understanding, summarize_file


class RepositoryUnderstandingTest(unittest.TestCase):
    def test_project_overview_uses_readme_manifest_and_extracted_graph_facts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_text(
                "# Weather service\n\nFetches weather data for a city.\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("fastapi==0.1\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "app.py").write_text(
                '"""HTTP entry point."""\n\nimport fastapi\n\nif __name__ == "__main__":\n    run()\n',
                encoding="utf-8",
            )
            analysis = {"files": [{
                "file": "app.py", "classes": [], "functions": ["run"],
                "methods": [], "imports": ["fastapi"],
            }]}
            graph = {
                "nodes": [
                    {"id": "file:app.py", "type": "FILE", "name": "app.py"},
                    {"id": "module:fastapi", "type": "MODULE", "name": "fastapi"},
                ],
                "relationships": [{
                    "source": "file:app.py", "relationship": "IMPORTS",
                    "target": "module:fastapi",
                }],
            }

            overview = build_project_understanding(root, analysis, graph, [])

        self.assertIn("Fetches weather data", overview["purpose"])
        self.assertIn("fastapi", overview["technologies"])
        self.assertEqual(1, overview["statistics"]["files"])
        self.assertEqual("Python __main__ guard", overview["entry_points"][0]["name"])
        self.assertIn("runtime", overview["architecture_note"])

    def test_overview_graph_counts_match_the_non_chunk_graph_view(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            overview = build_project_understanding(
                temporary_directory,
                {"files": []},
                {
                    "nodes": [
                        {"id": "file:app.py", "type": "FILE", "name": "app.py"},
                        {"id": "chunk:app.py:1", "type": "CODE_CHUNK", "name": "app.py"},
                    ],
                    "relationships": [{
                        "source": "file:app.py", "relationship": "HAS_CHUNK",
                        "target": "chunk:app.py:1",
                    }],
                },
                [{"id": "chunk:app.py:1"}],
            )

        self.assertEqual(1, overview["statistics"]["graph_nodes"])
        self.assertEqual(0, overview["statistics"]["relationships"])
        self.assertEqual(1, overview["statistics"]["code_chunks"])

    def test_file_summary_does_not_invent_purpose_without_docstring(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "mystery.py").write_text("def compute():\n    return 1\n", encoding="utf-8")
            analysis = {"files": [{
                "file": "mystery.py", "classes": [], "functions": ["compute"],
                "methods": [], "imports": [],
            }]}
            summary = summarize_file(root, "mystery.py", analysis, {
                "nodes": [{"id": "file:mystery.py", "type": "FILE", "name": "mystery.py"}],
                "relationships": [],
            })

        self.assertIn("Not enough information", summary["purpose"])
        self.assertEqual(["compute"], summary["functions"])

    def test_project_overview_keeps_setup_docs_separate_from_project_purpose(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "docs").mkdir()
            (root / "docs" / "overview.md").write_text(
                "# System notes\n\nThis service reads sensor events and stores them.\n",
                encoding="utf-8",
            )
            overview = build_project_understanding(root, {"files": []}, {"nodes": [], "relationships": []}, [])

        self.assertIn("Not enough information", overview["purpose"])
        self.assertIsNone(overview["purpose_evidence"])
        self.assertIn("sensor events", overview["documentation_evidence"][0]["excerpt"])

    def test_file_summary_includes_actual_class_docstrings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                "class Session:\n    \"\"\"Stores an active client session.\"\"\"\n    pass\n",
                encoding="utf-8",
            )
            summary = summarize_file(root, "service.py", {"files": [{
                "file": "service.py", "classes": ["Session"], "functions": [],
                "methods": [], "imports": [],
            }]}, {"nodes": [], "relationships": []})

        self.assertEqual("Stores an active client session.", summary["documented_components"][0]["purpose"])

    def test_file_summary_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaises(ValueError):
                summarize_file(root, "../outside.py", {"files": []}, {"nodes": [], "relationships": []})


if __name__ == "__main__":
    unittest.main()
