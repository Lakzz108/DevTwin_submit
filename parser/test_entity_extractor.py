import sys
import unittest
from pathlib import Path

from entity_extractor import extract_entities


class EntityExtractorTest(unittest.TestCase):
    def test_extracts_python_classes_methods_functions_imports_and_relationships(self):
        sample = Path(__file__).with_name("sample_code.py")
        result = extract_entities(str(sample))
        entities = result["entities"]
        relationships = {(item["relationship"], item["target"]) for item in result["relationships"]}

        self.assertIn("User", entities["classes"])
        self.assertIn("User.login", entities["methods"])
        self.assertIn("authenticate", entities["functions"])
        self.assertIn(("DEFINES", "User"), relationships)
        self.assertIn(("HAS_METHOD", "User.login"), relationships)


def _print_extraction(file_path):
    result = extract_entities(file_path)
    entities = result["entities"]
    print("EXTRACTED ENTITIES")
    for key in ("classes", "interfaces", "functions", "methods", "imports"):
        print(f"{key.title()}: {entities.get(key, [])}")
    print("RELATIONSHIPS")
    for edge in result["relationships"]:
        print(f"{edge['source']} --[{edge['relationship']}]--> {edge['target']}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _print_extraction(sys.argv[1])
    else:
        unittest.main()
