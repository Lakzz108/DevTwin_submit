import unittest

from neo4j_vector_store import (
    EMBEDDING_DIMENSIONS,
    VECTOR_INDEX_NAME,
    Neo4jVectorStore,
)


class FakeRecord(dict):
    def data(self):
        return dict(self)


class FakeDriver:
    def __init__(self, update_count=1, records=None):
        self.update_count = update_count
        self.records = records or []
        self.calls = []

    def execute_query(self, query, **parameters):
        self.calls.append((query, parameters))
        if "RETURN count(chunk) AS updated" in query:
            return [FakeRecord({"updated": self.update_count})], None, None
        return self.records, None, None


class Neo4jVectorStoreTest(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self.store = Neo4jVectorStore(self.driver)

    def test_creates_vector_index(self):
        self.store.ensure_index()
        query, _ = self.driver.calls[0]
        self.assertIn(VECTOR_INDEX_NAME, query)
        self.assertIn(str(EMBEDDING_DIMENSIONS), query)
        self.assertIn("CODE_CHUNK", query)

    def test_stores_repository_scoped_embedding(self):
        count = self.store.store_embeddings(
            "repo-1",
            [{"id": "chunk:a.py:FUNCTION:f:1:part-1", "embedding": [0.1] * EMBEDDING_DIMENSIONS}],
        )
        query, parameters = self.driver.calls[0]
        self.assertEqual(1, count)
        self.assertIn("chunk.repository_id = $repository_id", query)
        self.assertEqual(
            "repo-1::chunk:a.py:FUNCTION:f:1:part-1",
            parameters["rows"][0]["id"],
        )

    def test_rejects_wrong_vector_dimension(self):
        with self.assertRaises(ValueError):
            self.store.store_embeddings("repo-1", [{"id": "c1", "embedding": [0.1]}])
        self.assertEqual([], self.driver.calls)

    def test_search_is_scoped_and_returns_chunk_context(self):
        expected = {"id": "chunk:a.py", "file": "a.py", "score": 0.9}
        driver = FakeDriver(records=[FakeRecord(expected)])
        store = Neo4jVectorStore(driver)

        result = store.search("repo-1", [0.2] * EMBEDDING_DIMENSIONS, top_k=3)

        self.assertEqual([expected], result)
        query, parameters = driver.calls[0]
        self.assertIn("node.repository_id = $repository_id", query)
        self.assertEqual("repo-1", parameters["repository_id"])
        self.assertEqual(3, parameters["top_k"])


if __name__ == "__main__":
    unittest.main()
