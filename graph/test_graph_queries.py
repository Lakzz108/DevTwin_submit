import unittest

from graph_queries import (
    find_dependencies,
    find_dependents,
    find_impact,
    find_relationship_path,
)


class GraphQueriesTest(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "nodes": [
                {"id": "file:a.py", "type": "FILE", "name": "a.py"},
                {"id": "file:b.py", "type": "FILE", "name": "b.py"},
                {"id": "file:c.py", "type": "FILE", "name": "c.py"},
                {"id": "module:json", "type": "MODULE", "name": "json"},
            ],
            "relationships": [
                {"source": "file:a.py", "relationship": "IMPORTS", "target": "file:b.py"},
                {"source": "file:b.py", "relationship": "IMPORTS", "target": "file:c.py"},
                {"source": "file:a.py", "relationship": "IMPORTS", "target": "module:json"},
            ],
        }

    def test_dependencies_and_dependents(self):
        dependencies = find_dependencies(self.graph, "file:a.py", max_depth=2)
        self.assertEqual(
            {("file:b.py", 1), ("file:c.py", 2), ("module:json", 1)},
            {(item["id"], item["depth"]) for item in dependencies},
        )

        dependents = find_dependents(self.graph, "file:c.py", max_depth=2)
        self.assertEqual(
            {("file:b.py", 1), ("file:a.py", 2)},
            {(item["id"], item["depth"]) for item in dependents},
        )

    def test_path_and_impact(self):
        path = find_relationship_path(self.graph, "a.py", "file:c.py")
        self.assertEqual(
            [
                ("file:a.py", "IMPORTS", "file:b.py"),
                ("file:b.py", "IMPORTS", "file:c.py"),
            ],
            [(edge["source"], edge["relationship"], edge["target"]) for edge in path],
        )

        impacted = find_impact(self.graph, "file:c.py", max_depth=2)
        self.assertEqual(
            {"file:a.py", "file:b.py"},
            {node["id"] for node in impacted},
        )

    def test_ambiguous_names_are_rejected(self):
        self.graph["nodes"].append(
            {"id": "other:a.py", "type": "FILE", "name": "a.py"}
        )
        with self.assertRaises(ValueError):
            find_dependencies(self.graph, "a.py")


if __name__ == "__main__":
    unittest.main()
