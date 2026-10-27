import unittest

from neo4j_queries import Neo4jGraphReader


class FakeRecord(dict):
    def data(self):
        return dict(self)


class FakePath:
    def __init__(self, relationships):
        self.relationships = relationships


class FakeRelationship:
    def __init__(self, source, relationship_type, target):
        self.start_node = {"local_id": source}
        self.type = relationship_type
        self.end_node = {"local_id": target}


class FakeDriver:
    def __init__(self, records=None):
        self.records = records or []
        self.calls = []

    def execute_query(self, query, **parameters):
        self.calls.append((query, parameters))
        return self.records, None, None


class SequenceDriver(FakeDriver):
    def __init__(self, result_sets):
        super().__init__()
        self.result_sets = list(result_sets)

    def execute_query(self, query, **parameters):
        self.calls.append((query, parameters))
        return self.result_sets.pop(0), None, None


class Neo4jGraphReaderTest(unittest.TestCase):
    def test_dependencies_are_scoped_and_limited(self):
        expected = {"id": "file:b.py", "type": "FILE", "name": "b.py", "depth": 1}
        driver = FakeDriver([FakeRecord(expected)])
        reader = Neo4jGraphReader(driver)

        result = reader.find_dependencies("repo-1", "file:a.py", max_depth=2)

        self.assertEqual([expected], result)
        query, parameters = driver.calls[0]
        self.assertIn("(start)-[*1..2]->(target)", query)
        self.assertEqual("repo-1::file:a.py", parameters["start_id"])
        self.assertEqual("repo-1", parameters["repository_id"])

    def test_reverse_query_and_relationship_path(self):
        driver = FakeDriver([
            FakeRecord({
                "path": FakePath([
                    FakeRelationship("file:a.py", "IMPORTS", "file:b.py"),
                ]),
            }),
        ])
        reader = Neo4jGraphReader(driver)

        path = reader.find_relationship_path(
            "repo-1",
            "file:a.py",
            "file:b.py",
        )
        self.assertEqual(
            [{
                "source": "file:a.py",
                "relationship": "IMPORTS",
                "target": "file:b.py",
            }],
            path,
        )

        reader.find_dependents("repo-1", "file:b.py")
        self.assertIn("(target)-[*1..1]->(start)", driver.calls[1][0])

        reader.find_impact("repo-1", "file:b.py", max_depth=3)
        impact_query, impact_parameters = driver.calls[2]
        self.assertIn("all(edge IN relationships(path)", impact_query)
        self.assertIn("IMPORTS", impact_parameters["relationship_types"])

    def test_invalid_depth_is_rejected_before_query(self):
        driver = FakeDriver()
        reader = Neo4jGraphReader(driver)

        with self.assertRaises(ValueError):
            reader.find_dependencies("repo-1", "file:a.py", max_depth=1000)
        self.assertEqual([], driver.calls)

    def test_returns_structural_repository_graph_without_chunks(self):
        driver = SequenceDriver([
            [FakeRecord({"total": 2})],
            [
                FakeRecord({"id": "file:a.py", "type": "FILE", "name": "a.py", "file": "a.py"}),
                FakeRecord({"id": "function:a.py:run", "type": "FUNCTION", "name": "run", "file": "a.py"}),
            ],
            [FakeRecord({"total": 1})],
            [FakeRecord({
                "source": "file:a.py",
                "relationship": "DEFINES",
                "target": "function:a.py:run",
            })],
        ])
        reader = Neo4jGraphReader(driver)

        result = reader.get_repository_graph("repo-1", limit=2)

        self.assertEqual(2, result["total_nodes"])
        self.assertEqual(1, result["total_relationships"])
        self.assertFalse(result["truncated"])
        self.assertEqual("DEFINES", result["relationships"][0]["relationship"])
        self.assertIn("node.type <> 'CODE_CHUNK'", driver.calls[1][0])
        self.assertEqual(
            ["repo-1::file:a.py", "repo-1::function:a.py:run"],
            driver.calls[3][1]["node_ids"],
        )

    def test_repository_graph_rejects_invalid_limits(self):
        driver = FakeDriver()
        reader = Neo4jGraphReader(driver)

        with self.assertRaises(ValueError):
            reader.get_repository_graph("repo-1", limit=501)
        self.assertEqual([], driver.calls)


if __name__ == "__main__":
    unittest.main()
