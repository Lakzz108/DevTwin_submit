"""Focused tests for the DevTwin FastAPI routes."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from backend import main


class FakeWriter:
    def __init__(self):
        self.driver = object()
        self.database = "neo4j"
        self.closed = False
        self.graph = None

    def write_graph(self, repository_id, graph):
        self.graph = graph
        return {"nodes_processed": len(graph["nodes"]), "relationships_processed": len(graph["relationships"])}

    def close(self):
        self.closed = True


class FakeEmbeddingProvider:
    def embed_chunks(self, chunks):
        return [{"id": chunk["id"], "embedding": [0.0] * 384} for chunk in chunks]


class FakeVectorStore:
    def __init__(self, driver, database):
        self.items = 0

    def ensure_index(self):
        pass

    def store_embeddings(self, repository_id, items):
        self.items = len(items)
        return self.items


class FakeGraphReader:
    def __init__(self, driver, database):
        pass

    def get_repository_graph(self, repository_id, limit=300, include_chunks=False):
        return {
            "nodes": [{"id": "file:a.py", "type": "FILE", "name": "a.py", "file": "a.py"}],
            "relationships": [{
                "source": "file:a.py",
                "relationship": "IMPORTS",
                "target": "file:b.py",
            }],
            "total_nodes": 1,
            "total_relationships": 1,
            "truncated": False,
            "include_chunks": include_chunks,
        }

class BackendApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def test_health_route(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIn("embedding_model", response.json())

    def test_invalid_repository_path_is_rejected(self):
        response = self.client.post(
            "/repositories",
            json={"path": "/path/that/does/not/exist"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Traceback", response.text)

    def test_missing_repository_path_has_a_readable_validation_message(self):
        response = self.client.post("/repositories", json={})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Please provide a repository folder path.",
        )

    def test_empty_repository_is_rejected_before_database_access(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(main, "open_writer") as open_writer:
                response = self.client.post(
                    "/repositories",
                    json={"path": temp_dir},
                )

        self.assertEqual(response.status_code, 422)
        self.assertIn("No supported source files", response.json()["detail"])
        open_writer.assert_not_called()

    def test_neo4j_unavailable_is_a_readable_service_error(self):
        with patch.object(
            main.Neo4jGraphWriter,
            "from_env",
            side_effect=ServiceUnavailable("private connection detail"),
        ):
            response = self.client.get("/repositories/repo-1/graph")

        self.assertEqual(response.status_code, 503)
        self.assertIn("Neo4j is unavailable", response.json()["detail"])
        self.assertNotIn("private connection detail", response.text)
        self.assertNotIn("Traceback", response.text)

    def test_unexpected_api_failure_does_not_expose_traceback(self):
        class BrokenGraphReader(FakeGraphReader):
            def get_repository_graph(self, repository_id, limit=300, include_chunks=False):
                raise RuntimeError("private internal failure")

        with (
            patch.object(main, "open_writer", return_value=FakeWriter()),
            patch.object(main, "Neo4jGraphReader", BrokenGraphReader),
        ):
            response = self.client.get("/repositories/repo-1/graph")

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private internal failure", response.text)
        self.assertNotIn("Traceback", response.text)

    def test_repository_graph_route_returns_nodes_and_relationships(self):
        writer = FakeWriter()
        with (
            patch.object(main, "open_writer", return_value=writer),
            patch.object(main, "Neo4jGraphReader", FakeGraphReader),
        ):
            response = self.client.get("/repositories/repo-1/graph?limit=50")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nodes"][0]["type"], "FILE")
        self.assertEqual(
            response.json()["relationships"][0]["relationship"],
            "IMPORTS",
        )
        self.assertTrue(writer.closed)

    def test_dependency_endpoint_returns_file_and_module_dependencies_only(self):
        class DependencyReader(FakeGraphReader):
            def find_dependencies(self, repository_id, local_id, max_depth=1):
                return [
                    {"id": "file:models.py", "type": "FILE", "name": "models.py", "file": "models.py", "depth": 1},
                    {"id": "module:external", "type": "MODULE", "name": "external", "file": None, "depth": 1},
                    {"id": "chunk:auth.py", "type": "CODE_CHUNK", "name": "auth.py", "file": "auth.py", "depth": 1},
                    {"id": "class:Auth", "type": "CLASS", "name": "Auth", "file": "auth.py", "depth": 1},
                ]

        writer = FakeWriter()
        with (
            patch.object(main, "open_writer", return_value=writer),
            patch.object(main, "Neo4jGraphReader", DependencyReader),
        ):
            response = self.client.get(
                "/repositories/repo-1/dependencies",
                params={"file": "auth.py"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [node["type"] for node in response.json()["dependencies"]],
            ["FILE", "MODULE"],
        )

    def test_open_existing_repository_uses_path_instead_of_repository_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            writer = FakeWriter()
            with (
                patch.object(main, "open_writer", return_value=writer),
                patch.object(main, "Neo4jGraphReader", FakeGraphReader),
            ):
                response = self.client.post(
                    "/repositories/open",
                    json={"path": temp_dir},
                )

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                response.json()["repository_id"],
                main.make_repository_id(temp_dir),
            )
            self.assertEqual(response.json()["graph"]["nodes"][0]["type"], "FILE")
            self.assertTrue(writer.closed)

    def test_blank_query_is_rejected_by_request_validation(self):
        response = self.client.post(
            "/repositories/repo-1/query",
            json={"question": "   "},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Please enter a question first.")

    def test_ingests_local_python_repository(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "example.py"
            source_file.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
            writer = FakeWriter()

            with (
                patch.object(main, "open_writer", return_value=writer),
                patch.object(main, "get_embedding_provider", return_value=FakeEmbeddingProvider()),
                patch.object(main, "Neo4jVectorStore", FakeVectorStore),
            ):
                response = self.client.post(
                    "/repositories",
                    json={"path": temp_dir, "repository_id": "test-repo"},
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["repository_id"], "test-repo")
        self.assertEqual(response.json()["files_analyzed"], 1)
        self.assertGreaterEqual(response.json()["chunks_embedded"], 1)
        self.assertTrue(writer.closed)

    def test_frontend_origin_is_allowed_by_cors(self):
        response = self.client.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://127.0.0.1:5173",
        )

        fallback_port_response = self.client.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(fallback_port_response.status_code, 200)
        self.assertEqual(
            fallback_port_response.headers.get("access-control-allow-origin"),
            "http://127.0.0.1:5174",
        )


if __name__ == "__main__":
    unittest.main()
