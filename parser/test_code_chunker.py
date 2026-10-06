import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from code_chunker import build_code_chunks


class CodeChunkerTest(unittest.TestCase):
    def test_extracts_symbol_chunks_with_source_metadata(self):
        source = (
            "import os\n\n"
            "class Account:\n"
            "    def login(self):\n"
            "        return True\n\n"
            "def helper():\n"
            "    return 1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "account.py"
            file_path.write_text(source, encoding="utf-8")
            chunks = build_code_chunks(file_path, repository_id="repo-1")

        symbols = {(chunk["kind"], chunk["symbol"]) for chunk in chunks}
        self.assertIn(("CLASS", "Account"), symbols)
        self.assertIn(("METHOD", "Account.login"), symbols)
        self.assertIn(("FUNCTION", "helper"), symbols)
        self.assertEqual("MODULE_CONTEXT", chunks[0]["kind"])
        method = next(chunk for chunk in chunks if chunk["symbol"] == "Account.login")
        self.assertEqual((4, 5), (method["start_line"], method["end_line"]))
        self.assertEqual("repo-1", method["repository_id"])

    def test_splits_large_symbols_with_overlap_and_unique_ids(self):
        source = "def long_function():\n" + "    value = 1\n" * 20 + "    return value\n"
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "large.py"
            file_path.write_text(source, encoding="utf-8")
            chunks = build_code_chunks(file_path, max_characters=60)

        function_chunks = [chunk for chunk in chunks if chunk["kind"] == "FUNCTION"]
        self.assertGreater(len(function_chunks), 1)
        self.assertTrue(all(len(chunk["content"]) <= 60 for chunk in function_chunks))
        self.assertEqual(
            len(function_chunks),
            len({chunk["id"] for chunk in function_chunks}),
        )
        self.assertTrue(
            all(function_chunks[index]["start_line"] < function_chunks[index + 1]["start_line"]
                for index in range(len(function_chunks) - 1))
        )

    def test_rejects_nonpositive_chunk_limit(self):
        with self.assertRaises(ValueError):
            build_code_chunks("unused.py", max_characters=0)

    def test_line_ranges_are_correct_for_utf8_source(self):
        source = "# café\n\ndef greet():\n    return '👋'\n"
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "utf8.py"
            file_path.write_text(source, encoding="utf-8")
            chunks = build_code_chunks(file_path)

        function = next(chunk for chunk in chunks if chunk["symbol"] == "greet")
        self.assertEqual((3, 4), (function["start_line"], function["end_line"]))

    def test_parallel_repository_parses_use_independent_parser_instances(self):
        source = "class Account:\n    def login(self):\n        return True\n"
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "account.py"
            file_path.write_text(source, encoding="utf-8")
            with ThreadPoolExecutor(max_workers=6) as executor:
                results = list(executor.map(
                    lambda _: build_code_chunks(file_path),
                    range(24),
                ))

        self.assertEqual(24, len(results))
        for chunks in results:
            self.assertIn(
                ("METHOD", "Account.login"),
                {(chunk["kind"], chunk["symbol"]) for chunk in chunks},
            )


if __name__ == "__main__":
    unittest.main()
