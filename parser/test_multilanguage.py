import unittest
from pathlib import Path

from code_parser import parse_source_file
from entity_extractor import extract_entities
from graph_builder import build_graph_data
from language_detector import detect_language
from repository_analyzer import analyze_repository


PARSER_DIR = Path(__file__).resolve().parent
FIXTURES = PARSER_DIR / "fixtures" / "multilanguage"


class LanguageDetectionTest(unittest.TestCase):
    def test_supported_extensions(self):
        expected = {
            "a.py": "python",
            "a.js": "javascript",
            "a.jsx": "javascript",
            "a.ts": "typescript",
            "a.tsx": "typescript",
            "a.java": "java",
            "a.c": "c",
            "a.h": "c",
            "a.cpp": "cpp",
            "a.hpp": "cpp",
            "a.go": "go",
        }
        for file_name, language in expected.items():
            with self.subTest(file_name=file_name):
                self.assertEqual(detect_language(file_name), language)
        self.assertIsNone(detect_language("a.cs"))


class MultilanguageParsingTest(unittest.TestCase):
    def test_each_supported_language_parses_and_extracts_entities(self):
        samples = {
            "python": PARSER_DIR / "sample_code.py",
            "javascript": FIXTURES / "sample.js",
            "typescript": FIXTURES / "sample.ts",
            "java": FIXTURES / "Sample.java",
            "c": FIXTURES / "sample.c",
            "cpp": FIXTURES / "sample.cpp",
            "go": FIXTURES / "sample.go",
        }

        for language, file_path in samples.items():
            with self.subTest(language=language):
                detected, tree = parse_source_file(str(file_path))
                result = extract_entities(str(file_path))
                self.assertEqual(detected, language)
                self.assertFalse(tree.root_node.has_error)
                self.assertTrue(
                    result["entities"]["classes"]
                    or result["entities"]["functions"]
                    or result["entities"]["methods"]
                )
                self.assertIn("imports", result["entities"])

    def test_jsx_and_tsx_grammars_parse(self):
        for file_name, language in (
            ("sample.jsx", "javascript"),
            ("sample.tsx", "typescript"),
        ):
            with self.subTest(file_name=file_name):
                detected, tree = parse_source_file(str(FIXTURES / file_name))
                self.assertEqual(detected, language)
                self.assertFalse(tree.root_node.has_error)
                self.assertIn("Panel", extract_entities(str(FIXTURES / file_name))["entities"]["functions"])

    def test_non_python_samples_have_structural_relationships(self):
        samples = (
            FIXTURES / "sample.js",
            FIXTURES / "sample.ts",
            FIXTURES / "Sample.java",
            FIXTURES / "sample.c",
            FIXTURES / "sample.cpp",
            FIXTURES / "sample.go",
        )
        for file_path in samples:
            with self.subTest(file_path=file_path.name):
                result = extract_entities(str(file_path))
                relationships = result["relationships"]
                self.assertTrue(relationships)
                self.assertTrue(any(r["relationship"] == "IMPORTS" for r in relationships))

    def test_expected_constructs_are_extracted(self):
        expected = {
            "sample.js": ("Greeter", "run", "Greeter.greet"),
            "sample.ts": ("Greeter", "run", "Greeter.greet"),
            "Sample.java": ("Greeter", None, "Greeter.greet"),
            "sample.c": ("Greeter", "greet", None),
            "sample.cpp": ("Greeter", "run", "Greeter.greet"),
            "sample.go": ("Greeter", "main", "Greeter.Greet"),
        }
        for file_name, (class_name, function_name, method_name) in expected.items():
            with self.subTest(file_name=file_name):
                result = extract_entities(str(FIXTURES / file_name))["entities"]
                self.assertIn(class_name, result["classes"])
                if function_name:
                    self.assertIn(function_name, result["functions"])
                if method_name:
                    self.assertIn(method_name, result["methods"])

    def test_relative_javascript_import_resolves_to_file_node(self):
        analysis = analyze_repository(FIXTURES)
        graph = build_graph_data(analysis)
        helper_id = "file:helper.js"
        self.assertIn(helper_id, {node["id"] for node in graph["nodes"]})
        self.assertTrue(any(
            edge["source"] == "file:sample.js"
            and edge["relationship"] == "IMPORTS"
            and edge["target"] == helper_id
            for edge in graph["relationships"]
        ))


if __name__ == "__main__":
    unittest.main()
