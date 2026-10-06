import unittest

from embedding_service import (
    EMBEDDING_DIMENSIONS,
    FastEmbedEmbeddingProvider,
    format_chunk_for_embedding,
)


class FakeModel:
    def __init__(self):
        self.calls = []

    def embed(self, texts, batch_size):
        self.calls.append((list(texts), batch_size))
        return [[float(len(text))] * EMBEDDING_DIMENSIONS for text in texts]


class EmbeddingServiceTest(unittest.TestCase):
    def test_batches_local_embeddings(self):
        model = FakeModel()
        provider = FastEmbedEmbeddingProvider(model=model, batch_size=2)

        vectors = provider.embed_texts(["first", "second", "third"])

        self.assertEqual(3, len(vectors))
        self.assertTrue(all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors))
        self.assertEqual(2, len(model.calls))
        self.assertEqual(2, model.calls[0][1])

    def test_uses_query_and_passage_prefixes(self):
        model = FakeModel()
        provider = FastEmbedEmbeddingProvider(model=model)
        question_vector = provider.embed_query("Where is login implemented?")
        chunk = {
            "id": "c1",
            "file": "src/auth.py",
            "kind": "FUNCTION",
            "symbol": "login",
            "class_name": None,
            "start_line": 10,
            "end_line": 15,
            "content": "def login(): pass",
        }

        embedded_chunks = provider.embed_chunks([chunk])

        self.assertEqual(EMBEDDING_DIMENSIONS, len(question_vector))
        self.assertTrue(model.calls[0][0][0].startswith("query: "))
        self.assertTrue(model.calls[1][0][0].startswith("passage: "))
        self.assertEqual("c1", embedded_chunks[0]["id"])
        self.assertEqual(EMBEDDING_DIMENSIONS, len(embedded_chunks[0]["embedding"]))

    def test_chunk_metadata_is_added_to_embedding_input(self):
        chunk = {
            "file": "src/auth.py",
            "kind": "FUNCTION",
            "symbol": "login",
            "class_name": None,
            "start_line": 10,
            "end_line": 15,
            "content": "def login(): pass",
        }
        text = format_chunk_for_embedding(chunk)

        self.assertIn("File: src/auth.py", text)
        self.assertIn("Symbol: login", text)
        self.assertIn("Lines: 10-15", text)
        self.assertIn("def login(): pass", text)

    def test_rejects_empty_inputs_and_invalid_batch_size(self):
        provider = FastEmbedEmbeddingProvider(model=FakeModel())
        with self.assertRaises(ValueError):
            provider.embed_texts([""])
        with self.assertRaises(ValueError):
            FastEmbedEmbeddingProvider(model=FakeModel(), batch_size=0)


if __name__ == "__main__":
    unittest.main()
