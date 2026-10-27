import tempfile
import unittest
from pathlib import Path

from repository_analyzer import analyze_repository


class RepositoryAnalyzerLanguageTest(unittest.TestCase):
    def test_non_python_files_are_parsed_into_language_aware_symbols(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "src").mkdir()
            (root / "src" / "service.js").write_text(
                "export class Service { run() { return 1; } }\n",
                encoding="utf-8",
            )
            (root / "src" / "helper.py").write_text(
                "class Helper:\n    def run(self):\n        return 1\n",
                encoding="utf-8",
            )

            result = analyze_repository(root)

        by_file = {item["file"]: item for item in result["files"]}
        self.assertIn("src/service.js", by_file)
        self.assertEqual(["Service"], by_file["src/service.js"]["classes"])
        self.assertEqual(["Service.run"], by_file["src/service.js"]["methods"])
        self.assertEqual([], by_file["src/service.js"]["imports"])
        self.assertEqual(["Helper"], by_file["src/helper.py"]["classes"])


if __name__ == "__main__":
    unittest.main()
