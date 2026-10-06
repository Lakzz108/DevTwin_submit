"""Store and search code-chunk embeddings using Neo4j vector indexes."""

import math


VECTOR_INDEX_NAME = "devtwin_code_chunk_embedding_384"
VECTOR_PROPERTY = "embedding_384"
EMBEDDING_DIMENSIONS = 384


class Neo4jVectorStore:
    def __init__(self, driver, database="neo4j"):
        self.driver = driver
        self.database = database

    def ensure_index(self):
        """Create the code-chunk vector index if it is not already present."""

        query = (
            f"CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS "
            f"FOR (chunk:CODE_CHUNK) ON (chunk.{VECTOR_PROPERTY}) "
            "OPTIONS {indexConfig: {"
            f"`vector.dimensions`: {EMBEDDING_DIMENSIONS}, "
            "`vector.similarity_function`: 'cosine'}}"
        )
        self.driver.execute_query(query, database_=self.database)

    def store_embeddings(self, repository_id, items):
        """Attach vectors to existing code chunks, validating the whole batch."""

        rows = []
        for item in items:
            embedding = item["embedding"]
            if len(embedding) != EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"Expected {EMBEDDING_DIMENSIONS} embedding values, "
                    f"received {len(embedding)}"
                )
            if not all(math.isfinite(value) for value in embedding):
                raise ValueError("Embedding values must all be finite numbers")
            rows.append({
                "id": f"{repository_id}::{item['id']}",
                "embedding": embedding,
            })

        if not rows:
            return 0

        query = (
            "UNWIND $rows AS row "
            "MATCH (chunk:DevTwinEntity:CODE_CHUNK {id: row.id}) "
            "WHERE chunk.repository_id = $repository_id "
            f"SET chunk.{VECTOR_PROPERTY} = row.embedding "
            "RETURN count(chunk) AS updated"
        )
        records, _, _ = self.driver.execute_query(
            query,
            rows=rows,
            repository_id=repository_id,
            database_=self.database,
        )
        updated = records[0]["updated"] if records else 0
        if updated != len(rows):
            raise ValueError(
                f"Stored embeddings for {updated} of {len(rows)} requested chunks. "
                "Check that chunk IDs exist in this repository graph."
            )
        return updated

    def search(self, repository_id, query_embedding, top_k=5):
        """Return the most similar chunks within one repository."""

        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        if len(query_embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSIONS} query embedding values, "
                f"received {len(query_embedding)}"
            )
        if not all(math.isfinite(value) for value in query_embedding):
            raise ValueError("Query embedding values must all be finite numbers")

        query = (
            "CALL db.index.vector.queryNodes($index_name, $candidate_k, $embedding) "
            "YIELD node, score "
            "WHERE node.repository_id = $repository_id "
            "RETURN node.local_id AS id, node.file AS file, "
            "node.symbol AS symbol, node.symbol_kind AS kind, "
            "node.start_line AS start_line, node.end_line AS end_line, "
            "node.content AS content, score "
            "ORDER BY score DESC LIMIT $top_k"
        )
        records, _, _ = self.driver.execute_query(
            query,
            index_name=VECTOR_INDEX_NAME,
            candidate_k=min(top_k * 10, 1000),
            embedding=query_embedding,
            repository_id=repository_id,
            top_k=top_k,
            database_=self.database,
        )
        return [record.data() for record in records]
