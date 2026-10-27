import unittest

from neo4j_writer import Neo4jGraphWriter


class FakeTransaction:
    def __init__(self):
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))


class FakeSession:
    def __init__(self, transaction):
        self.transaction = transaction

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute_write(self, callback, *args):
        return callback(self.transaction, *args)


class FakeDriver:
    def __init__(self):
        self.transaction = FakeTransaction()
        self.queries = []

    def execute_query(self, query, **parameters):
        self.queries.append((query, parameters))

    def session(self, database):
        return FakeSession(self.transaction)

    def close(self):
        pass


class Neo4jGraphWriterTest(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "nodes": [
                {"id": "file:app.py", "type": "FILE", "name": "app.py"},
                {"id": "module:json", "type": "MODULE", "name": "json"},
            ],
            "relationships": [
                {
                    "source": "file:app.py",
                    "relationship": "IMPORTS",
                    "target": "module:json",
                },
            ],
        }
        self.driver = FakeDriver()
        self.writer = Neo4jGraphWriter(self.driver)

    def test_write_namespaces_nodes_and_creates_typed_relationship(self):
        result = self.writer.write_graph("repo-123", self.graph)

        self.assertEqual(
            {"nodes_processed": 2, "relationships_processed": 1},
            result,
        )
        self.assertEqual(1, len(self.driver.queries))
        self.assertIn("DETACH DELETE", self.driver.transaction.calls[0][0])
        self.assertIn(
            "entity:FILE",
            next(query for query, _ in self.driver.transaction.calls if "entity:FILE" in query),
        )
        relation_query, relation_parameters = self.driver.transaction.calls[-1]
        self.assertIn("[edge:IMPORTS]", relation_query)
        self.assertEqual(
            "repo-123::file:app.py",
            relation_parameters["rows"][0]["source_id"],
        )
        self.assertEqual("repo-123", relation_parameters["repository_id"])

    def test_rejects_invalid_relationship_type_before_database_write(self):
        invalid_graph = {
            "nodes": self.graph["nodes"],
            "relationships": [{
                "source": "file:app.py",
                "relationship": "IMPORTS]->(n)",
                "target": "module:json",
            }],
        }

        with self.assertRaises(ValueError):
            self.writer.write_graph("repo-123", invalid_graph)
        self.assertEqual([], self.driver.queries)

    def test_rejects_relationship_with_missing_endpoint(self):
        invalid_graph = {
            "nodes": self.graph["nodes"],
            "relationships": [{
                "source": "file:missing.py",
                "relationship": "IMPORTS",
                "target": "module:json",
            }],
        }

        with self.assertRaises(ValueError):
            self.writer.write_graph("repo-123", invalid_graph)
        self.assertEqual([], self.driver.queries)


if __name__ == "__main__":
    unittest.main()
