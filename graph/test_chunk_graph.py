import unittest

from chunk_graph import add_chunks_to_graph


class ChunkGraphTest(unittest.TestCase):
    def test_adds_chunk_and_file_symbol_edges(self):
        graph = {
            "nodes": [
                {"id": "file:src/user.py", "type": "FILE", "name": "user.py"},
                {"id": "class:src/user.py:User", "type": "CLASS", "name": "User"},
                {"id": "method:src/user.py:User.login", "type": "METHOD", "name": "User.login"},
            ],
            "relationships": [],
        }
        chunks = [{
            "id": "chunk:src/user.py:METHOD:User.login:4:part-1",
            "file": "src/user.py",
            "kind": "METHOD",
            "symbol": "User.login",
            "class_name": "User",
            "start_line": 4,
            "end_line": 5,
            "content": "def login(self): return True",
        }]

        result = add_chunks_to_graph(graph, chunks)

        chunk_node = next(node for node in result["nodes"] if node["type"] == "CODE_CHUNK")
        self.assertEqual((4, 5), (chunk_node["start_line"], chunk_node["end_line"]))
        self.assertEqual(
            {
                ("file:src/user.py", "CONTAINS_CHUNK", chunk_node["id"]),
                (chunk_node["id"], "DESCRIBES", "method:src/user.py:User.login"),
                ("method:src/user.py:User.login", "HAS_CHUNK", chunk_node["id"]),
            },
            {
                (edge["source"], edge["relationship"], edge["target"])
                for edge in result["relationships"]
            },
        )

    def test_does_not_duplicate_existing_chunks(self):
        chunk = {
            "id": "chunk:src/user.py:MODULE:1:part-1",
            "file": "src/user.py",
            "kind": "MODULE",
            "symbol": None,
            "start_line": 1,
            "end_line": 1,
            "content": "pass",
        }
        graph = {"nodes": [{"id": chunk["id"]}], "relationships": []}

        result = add_chunks_to_graph(graph, [chunk])

        self.assertEqual(1, len(result["nodes"]))
        self.assertEqual([], result["relationships"])


if __name__ == "__main__":
    unittest.main()
