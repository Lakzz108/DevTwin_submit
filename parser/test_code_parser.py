import tempfile
import unittest
from pathlib import Path

from code_parser import parse_python_file


class CodeParserTest(unittest.TestCase):
    def test_parses_python_source_into_a_module_tree(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sample.py"
            path.write_text("class User:\n    def login(self):\n        return True\n", encoding="utf-8")
            tree = parse_python_file(path)

        self.assertEqual("module", tree.root_node.type)
        self.assertFalse(tree.root_node.has_error)


if __name__ == "__main__":
    unittest.main()
