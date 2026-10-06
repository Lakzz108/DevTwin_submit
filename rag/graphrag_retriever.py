"""Combine semantic code search with neighborhood expansion in the graph."""


class GraphRAGRetriever:
    def __init__(self, embedding_provider, vector_store, graph_reader):
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.graph_reader = graph_reader

    def retrieve(self, repository_id, question, top_k=5):
        """Return semantic chunks plus their directly connected graph context."""

        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")

        query_vector = self.embedding_provider.embed_query(question)

        semantic_chunks = self.vector_store.search(
            repository_id,
            query_vector,
            top_k=top_k,
        )

        graph_nodes = {}
        graph_relationships = {}
        for chunk in semantic_chunks:
            chunk_id = chunk["id"]
            graph_nodes[chunk_id] = {
                "id": chunk_id,
                "type": "CODE_CHUNK",
                "name": chunk.get("symbol") or chunk.get("file"),
                "file": chunk.get("file"),
            }
            for neighbor in self.graph_reader.find_neighbors(repository_id, chunk_id):
                node_id = neighbor["id"]
                graph_nodes[node_id] = {
                    "id": node_id,
                    "type": neighbor.get("type"),
                    "name": neighbor.get("name"),
                    "file": neighbor.get("file"),
                }
                edge_key = (
                    neighbor["source"],
                    neighbor["relationship"],
                    neighbor["target"],
                )
                graph_relationships[edge_key] = {
                    "source": edge_key[0],
                    "relationship": edge_key[1],
                    "target": edge_key[2],
                }

        return {
            "semantic_chunks": semantic_chunks,
            "graph_context": {
                "nodes": list(graph_nodes.values()),
                "relationships": list(graph_relationships.values()),
            },
        }
