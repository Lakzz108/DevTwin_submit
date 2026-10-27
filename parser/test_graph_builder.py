import tempfile
import unittest
from pathlib import Path

from graph_builder import build_graph_data
from repository_analyzer import analyze_repository


class GraphBuilderTest(unittest.TestCase):
    def test_builds_project_file_symbol_and_import_relationships(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text(
                "from src.user import User\ndef main():\n    return User()\n",
                encoding="utf-8",
            )
            (root / "src" / "user.py").write_text(
                "class User:\n    def login(self):\n        return True\n",
                encoding="utf-8",
            )
            graph = build_graph_data(analyze_repository(root))

        nodes = {node["id"]: node for node in graph["nodes"]}
        edges = {(edge["source"], edge["relationship"], edge["target"]) for edge in graph["relationships"]}
        self.assertEqual("PROJECT", nodes["project:root"]["type"])
        self.assertIn(("file:src/main.py", "IMPORTS", "file:src/user.py"), edges)
        self.assertIn(("file:src/user.py", "DEFINES", "class:src/user.py:User"), edges)
        self.assertIn(("class:src/user.py:User", "HAS_METHOD", "method:src/user.py:User.login"), edges)


if __name__ == "__main__":
    unittest.main()
