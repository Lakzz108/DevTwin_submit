"""Graph retrieval queries backed by Neo4j."""


class Neo4jGraphReader:
    """Read dependencies, dependents, and paths for one repository graph."""

    def __init__(self, driver, database="neo4j"):
        self.driver = driver
        self.database = database

    @staticmethod
    def _validate_depth(max_depth):
        if not isinstance(max_depth, int) or not 1 <= max_depth <= 10:
            raise ValueError("max_depth must be an integer between 1 and 10")

    @staticmethod
    def _scoped_id(repository_id, local_id):
        if not isinstance(repository_id, str) or not repository_id.strip():
            raise ValueError("repository_id must be a non-empty string")
        if not isinstance(local_id, str) or not local_id.strip():
            raise ValueError("local_id must be a non-empty string")
        return f"{repository_id}::{local_id}"

    def _traverse(self, repository_id, local_id, max_depth, reverse):
        self._validate_depth(max_depth)
        start_id = self._scoped_id(repository_id, local_id)

        if reverse:
            path_pattern = f"(target)-[*1..{max_depth}]->(start)"
        else:
            path_pattern = f"(start)-[*1..{max_depth}]->(target)"

        query = (
            "MATCH (start:DevTwinEntity {id: $start_id}) "
            f"MATCH path = {path_pattern} "
            "WHERE target:DevTwinEntity "
            "AND target.repository_id = $repository_id "
            "AND target.id <> start.id "
            "WITH target, min(length(path)) AS depth "
            "RETURN target.local_id AS id, target.type AS type, "
            "target.name AS name, target.file AS file, depth "
            "ORDER BY depth, id"
        )
        records, _, _ = self.driver.execute_query(
            query,
            start_id=start_id,
            repository_id=repository_id,
            database_=self.database,
        )
        return [record.data() for record in records]

    def find_dependencies(self, repository_id, local_id, max_depth=1):
        """Return nodes reachable from the selected node."""

        return self._traverse(
            repository_id,
            local_id,
            max_depth,
            reverse=False,
        )

    def find_dependents(self, repository_id, local_id, max_depth=1):
        """Return nodes with a directed path to the selected node."""

        return self._traverse(
            repository_id,
            local_id,
            max_depth,
            reverse=True,
        )

    def find_impact(self, repository_id, local_id, max_depth=3):
        """Return reverse-reachable nodes as the graph's impact view."""

        return self.find_dependents(repository_id, local_id, max_depth=max_depth)

    def find_neighbors(self, repository_id, local_id):
        """Return directly connected nodes and the relationships to them."""

        start_id = self._scoped_id(repository_id, local_id)
        query = (
            "MATCH (start:DevTwinEntity {id: $start_id}) "
            "MATCH (start)-[relationship]-(neighbor:DevTwinEntity) "
            "WHERE neighbor.repository_id = $repository_id "
            "RETURN neighbor.local_id AS id, neighbor.type AS type, "
            "neighbor.name AS name, neighbor.file AS file, "
            "startNode(relationship).local_id AS source, "
            "type(relationship) AS relationship, "
            "endNode(relationship).local_id AS target"
        )
        records, _, _ = self.driver.execute_query(
            query,
            start_id=start_id,
            repository_id=repository_id,
            database_=self.database,
        )
        return [record.data() for record in records]

    def get_repository_graph(self, repository_id, limit=300, include_chunks=False):
        """Return repository structure, optionally including retrieval chunks."""

        if not isinstance(repository_id, str) or not repository_id.strip():
            raise ValueError("repository_id must be a non-empty string")
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500")
        if not isinstance(include_chunks, bool):
            raise ValueError("include_chunks must be a boolean")

        node_filter = "" if include_chunks else "WHERE node.type <> 'CODE_CHUNK' "
        relationship_filter = "" if include_chunks else (
            "AND source.type <> 'CODE_CHUNK' AND target.type <> 'CODE_CHUNK' "
        )

        node_count_query = (
            "MATCH (node:DevTwinEntity {repository_id: $repository_id}) "
            f"{node_filter}"
            "RETURN count(node) AS total"
        )
        count_records, _, _ = self.driver.execute_query(
            node_count_query,
            repository_id=repository_id,
            database_=self.database,
        )
        total_nodes = count_records[0]["total"] if count_records else 0

        node_query = (
            "MATCH (node:DevTwinEntity {repository_id: $repository_id}) "
            f"{node_filter}"
            "RETURN node.local_id AS id, node.type AS type, "
            "node.name AS name, node.file AS file "
            "ORDER BY node.type, node.name, node.local_id LIMIT $limit"
        )
        node_records, _, _ = self.driver.execute_query(
            node_query,
            repository_id=repository_id,
            limit=limit,
            database_=self.database,
        )
        nodes = [record.data() for record in node_records]
        node_ids = [node["id"] for node in nodes]

        relationship_count_query = (
            "MATCH (source:DevTwinEntity {repository_id: $repository_id}) "
            "-[relationship]->(target:DevTwinEntity {repository_id: $repository_id}) "
            f"WHERE true {relationship_filter}"
            "RETURN count(relationship) AS total"
        )
        relationship_count_records, _, _ = self.driver.execute_query(
            relationship_count_query,
            repository_id=repository_id,
            database_=self.database,
        )
        total_relationships = (
            relationship_count_records[0]["total"]
            if relationship_count_records
            else 0
        )

        relationships = []
        if node_ids:
            relationship_query = (
                "MATCH (source:DevTwinEntity {repository_id: $repository_id}) "
                "-[relationship]->(target:DevTwinEntity {repository_id: $repository_id}) "
                "WHERE source.id IN $node_ids AND target.id IN $node_ids "
                f"{relationship_filter}"
                "RETURN source.local_id AS source, type(relationship) AS relationship, "
                "target.local_id AS target "
                "ORDER BY source, relationship, target LIMIT $relationship_limit"
            )
            edge_records, _, _ = self.driver.execute_query(
                relationship_query,
                repository_id=repository_id,
                node_ids=[f"{repository_id}::{node_id}" for node_id in node_ids],
                relationship_limit=min(limit * 3, 1000),
                database_=self.database,
            )
            relationships = [record.data() for record in edge_records]

        return {
            "nodes": nodes,
            "relationships": relationships,
            "total_nodes": total_nodes,
            "total_relationships": total_relationships,
            "include_chunks": include_chunks,
            "truncated": (
                total_nodes > len(nodes)
                or total_relationships > len(relationships)
            ),
        }

    def find_relationship_path(
        self,
        repository_id,
        source_local_id,
        target_local_id,
        max_depth=10,
    ):
        """Return the shortest directed relationship path, or an empty list."""

        self._validate_depth(max_depth)
        source_id = self._scoped_id(repository_id, source_local_id)
        target_id = self._scoped_id(repository_id, target_local_id)
        query = (
            "MATCH (source:DevTwinEntity {id: $source_id}), "
            "(target:DevTwinEntity {id: $target_id}) "
            f"MATCH path = shortestPath((source)-[*..{max_depth}]->(target)) "
            "RETURN path"
        )
        records, _, _ = self.driver.execute_query(
            query,
            source_id=source_id,
            target_id=target_id,
            database_=self.database,
        )
        if not records:
            return []

        path = records[0]["path"]
        return [
            {
                "source": relationship.start_node["local_id"],
                "relationship": relationship.type,
                "target": relationship.end_node["local_id"],
            }
            for relationship in path.relationships
        ]
