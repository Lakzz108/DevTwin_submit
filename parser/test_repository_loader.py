import tempfile
import unittest
from pathlib import Path

from repository_loader import scan_repository


class RepositoryLoaderTest(unittest.TestCase):
    def test_scans_supported_source_files_and_skips_generated_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "src" / "App.tsx").write_text("export default function App() {}\n", encoding="utf-8")
            (root / "node_modules" / "pkg").mkdir(parents=True)
            (root / "node_modules" / "pkg" / "ignored.js").write_text("", encoding="utf-8")
            (root / "notes.txt").write_text("not source", encoding="utf-8")

            paths = {path.relative_to(root).as_posix() for path in scan_repository(root)}

        self.assertEqual({"src/main.py", "src/App.tsx"}, paths)

    def test_rejects_missing_and_non_directory_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "source.py"
            file_path.write_text("", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                scan_repository(file_path / "missing")
            with self.assertRaises(NotADirectoryError):
                scan_repository(file_path)


if __name__ == "__main__":
    unittest.main()
