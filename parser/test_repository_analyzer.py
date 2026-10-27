import tempfile
import unittest
from pathlib import Path

from repository_analyzer import analyze_repository


class RepositoryAnalyzerTest(unittest.TestCase):
    def test_analyzes_multiple_files_and_resolves_internal_imports(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text(
                "from app.service import run\ndef main():\n    return run()\n",
                encoding="utf-8",
            )
            (root / "app" / "service.py").write_text(
                "def run():\n    return True\n", encoding="utf-8"
            )

            result = analyze_repository(root)

        self.assertEqual(2, len(result["files"]))
        self.assertEqual(1, result["import_summary"]["internal"])
        by_path = {item["file"]: item for item in result["files"]}
        self.assertEqual(["main"], by_path["app/main.py"]["functions"])


if __name__ == "__main__":
    unittest.main()
