import unittest

from graphrag_retriever import GraphRAGRetriever


class FakeEmbeddingProvider:
    def embed_query(self, question):
        self.question = question
        return [0.2, 0.4]


class FakeVectorStore:
    def search(self, repository_id, query_embedding, top_k):
        self.arguments = (repository_id, query_embedding, top_k)
        return [{
            "id": "chunk:src/auth.py:FUNCTION:login:4:part-1",
            "file": "src/auth.py",
            "symbol": "login",
            "content": "def login(): ...",
            "score": 0.91,
        }]


class FakeGraphReader:
    def find_neighbors(self, repository_id, local_id):
        self.arguments = (repository_id, local_id)
        return [{
            "id": "function:src/auth.py:login",
            "type": "FUNCTION",
            "name": "login",
            "file": "src/auth.py",
            "source": local_id,
            "relationship": "DESCRIBES",
            "target": "function:src/auth.py:login",
        }]


class GraphRAGRetrieverTest(unittest.TestCase):
    def test_combines_vector_matches_with_graph_relationships(self):
        provider = FakeEmbeddingProvider()
        vector_store = FakeVectorStore()
        graph_reader = FakeGraphReader()
        retriever = GraphRAGRetriever(provider, vector_store, graph_reader)

        result = retriever.retrieve("repo-1", "Where is login implemented?", top_k=3)

        self.assertEqual("Where is login implemented?", provider.question)
        self.assertEqual(("repo-1", [0.2, 0.4], 3), vector_store.arguments)
        self.assertEqual("repo-1", graph_reader.arguments[0])
        self.assertEqual(1, len(result["semantic_chunks"]))
        self.assertEqual(2, len(result["graph_context"]["nodes"]))
        self.assertEqual("DESCRIBES", result["graph_context"]["relationships"][0]["relationship"])

    def test_rejects_blank_question(self):
        retriever = GraphRAGRetriever(
            FakeEmbeddingProvider(),
            FakeVectorStore(),
            FakeGraphReader(),
        )
        with self.assertRaises(ValueError):
            retriever.retrieve("repo-1", " ")


if __name__ == "__main__":
    unittest.main()
