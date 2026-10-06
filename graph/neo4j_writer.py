"""Persist graph data produced by ``build_graph_data`` in Neo4j."""

import os
import re
from collections import defaultdict
from pathlib import Path


NODE_TYPES = {"FILE", "CLASS", "FUNCTION", "METHOD", "MODULE", "CODE_CHUNK"}
RELATIONSHIP_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
CONSTRAINT_QUERY = (
    "CREATE CONSTRAINT devtwin_entity_id IF NOT EXISTS "
    "FOR (entity:DevTwinEntity) REQUIRE entity.id IS UNIQUE"
)


class Neo4jGraphWriter:
    """Write repository graph nodes and typed relationships to Neo4j."""

    def __init__(self, driver, database="neo4j"):
        self.driver = driver
        self.database = database

    @classmethod
    def from_env(cls):
        """Create a connected writer using the project-root ``.env`` file."""

        try:
            from dotenv import load_dotenv
            from neo4j import GraphDatabase
        except ImportError as error:
            raise RuntimeError(
                "Neo4j support dependencies are missing. Run "
                "'.venv/bin/pip install -r requirements.txt'."
            ) from error

        project_root = Path(__file__).resolve().parents[1]
        load_dotenv(project_root / ".env")

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        database = os.getenv("NEO4J_DATABASE", "neo4j")

        if not password:
            raise RuntimeError(
                "NEO4J_PASSWORD is not set. Add your Neo4j Desktop password "
                "to the project-root .env file."
            )

        driver = GraphDatabase.driver(uri, auth=(username, password))
        try:
            driver.verify_connectivity()
        except Exception:
            driver.close()
            raise
        return cls(driver, database=database)

    def close(self):
        self.driver.close()

    def write_graph(self, repository_id, graph_data):
        """Upsert one repository graph and return the number of processed rows.

        IDs are namespaced by repository_id so two repositories can contain
        files with the same relative path without colliding in Neo4j.
        """

        prepared_nodes, prepared_relationships = self._prepare_graph(
            repository_id,
            graph_data,
        )

        self.driver.execute_query(
            CONSTRAINT_QUERY,
            database_=self.database,
        )

        with self.driver.session(database=self.database) as session:
            session.execute_write(
                self._write_transaction,
                prepared_nodes,
                prepared_relationships,
                repository_id,
            )

        return {
            "nodes_processed": len(prepared_nodes),
            "relationships_processed": len(prepared_relationships),
        }

    @staticmethod
    def _prepare_graph(repository_id, graph_data):
        if not isinstance(repository_id, str) or not repository_id.strip():
            raise ValueError("repository_id must be a non-empty string")

        node_ids = set()
        prepared_nodes = []
        for node in graph_data["nodes"]:
            node_type = node["type"]
            if node_type not in NODE_TYPES:
                raise ValueError(f"Unsupported graph node type: {node_type}")

            local_id = node["id"]
            node_ids.add(local_id)
            properties = {
                "id": f"{repository_id}::{local_id}",
                "repository_id": repository_id,
                "local_id": local_id,
                "type": node_type,
                "name": node["name"],
            }
            if "file" in node:
                properties["file"] = node["file"]
            for property_name in (
                "symbol_kind",
                "symbol",
                "class_name",
                "start_line",
                "end_line",
                "content",
            ):
                if node.get(property_name) is not None:
                    properties[property_name] = node[property_name]
            prepared_nodes.append({"label": node_type, "properties": properties})

        prepared_relationships = []
        for relationship in graph_data["relationships"]:
            relationship_type = relationship["relationship"]
            if not RELATIONSHIP_TYPE_PATTERN.fullmatch(relationship_type):
                raise ValueError(
                    f"Unsupported graph relationship type: {relationship_type}"
                )
            source = relationship["source"]
            target = relationship["target"]
            if source not in node_ids or target not in node_ids:
                raise ValueError(
                    f"Relationship endpoint missing from graph nodes: "
                    f"{source} -> {target}"
                )
            prepared_relationships.append({
                "source_id": f"{repository_id}::{source}",
                "target_id": f"{repository_id}::{target}",
                "type": relationship_type,
            })

        return prepared_nodes, prepared_relationships

    @staticmethod
    def _write_transaction(tx, nodes, relationships, repository_id):
        nodes_by_type = defaultdict(list)
        for node in nodes:
            nodes_by_type[node["label"]].append(node["properties"])

        for node_type, rows in nodes_by_type.items():
            # The label comes from the fixed NODE_TYPES allow-list.
            tx.run(
                f"UNWIND $rows AS row "
                f"MERGE (entity:DevTwinEntity {{id: row.id}}) "
                f"SET entity:{node_type} "
                "SET entity += row",
                rows=rows,
            )

        relationships_by_type = defaultdict(list)
        for relationship in relationships:
            relationships_by_type[relationship["type"]].append(relationship)

        for relationship_type, rows in relationships_by_type.items():
            # Relationship types are checked against a strict identifier pattern.
            tx.run(
                f"UNWIND $rows AS row "
                "MATCH (source:DevTwinEntity {id: row.source_id}) "
                "MATCH (target:DevTwinEntity {id: row.target_id}) "
                f"MERGE (source)-[edge:{relationship_type}]->(target) "
                "SET edge.repository_id = $repository_id",
                rows=rows,
                repository_id=repository_id,
            )
