import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from import_resolver import resolve_imports
from repository_analyzer import analyze_repository


class ImportResolverTest(unittest.TestCase):
    def test_python_absolute_from_and_relative_import_forms_resolve(self):
        sources = {
            "pkg/__init__.py": "",
            "pkg/mod.py": "class Model: pass\n",
            "pkg/child.py": "def child(): pass\n",
            "pkg/root.py": "class Root: pass\n",
            "pkg/sub/__init__.py": "",
            "pkg/sub/local.py": "def local(): pass\n",
            "pkg/sub/consumer.py": (
                "import pkg.mod as mod\n"
                "import pkg.child\n"
                "from pkg import mod as imported_mod\n"
                "from .local import local\n"
                "from ..root import Root\n"
            ),
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for filename, content in sources.items():
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            analysis = analyze_repository(root)

        consumer = next(item for item in analysis["files"] if item["file"] == "pkg/sub/consumer.py")
        resolved = {
            (record["module"], record["kind"], record.get("target_file"), record["resolution"])
            for record in consumer["import_records"]
        }
        self.assertIn(("pkg.mod", "python_import", "pkg/mod.py", "internal"), resolved)
        self.assertIn(("pkg.child", "python_import", "pkg/child.py", "internal"), resolved)
        self.assertIn(("pkg", "python_from", "pkg/mod.py", "internal"), resolved)
        self.assertIn(("local", "python_from", "pkg/sub/local.py", "internal"), resolved)
        self.assertIn(("root", "python_from", "pkg/root.py", "internal"), resolved)
        self.assertGreater(analysis["import_summary"]["internal"], 0)


if __name__ == "__main__":
    unittest.main()
