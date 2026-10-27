import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph_builder import build_graph_data
from repository_chunker import build_repository_chunks
from repository_analyzer import analyze_repository
from graph.chunk_graph import add_chunks_to_graph


class RepositoryGraphIntegrationTest(unittest.TestCase):
    def test_multilanguage_repository_produces_grounded_relationships(self):
        sources = {
            "app/__init__.py": "",
            "app/main.py": (
                "from app.services.auth import authenticate\n"
                "from app.models.user import User\n"
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                "def login():\n    authenticate()\n    return User()\n\n"
                "@app.get('/login')\n"
                "def login_endpoint():\n    return login()\n"
            ),
            "app/services/auth.py": (
                "from ..models.user import User\n\n"
                "def authenticate():\n    return User()\n"
            ),
            "app/models/user.py": (
                "class BaseUser:\n    pass\n\n"
                "class User(BaseUser):\n    def validate(self):\n        return True\n"
            ),
            "web/src/main.jsx": "import App from './App';\nexport function mount(){ App(); }\n",
            "web/src/App.jsx": "import { helper } from './helper.js';\nexport default function App(){ helper(); }\n",
            "web/src/helper.js": "export function helper(){ return true; }\n",
            "web/src/routes.js": "const express = require('express');\nconst app = express();\napp.get('/items', listItems);\nfunction listItems(){ return []; }\n",
            "web/src/types/user.ts": "export interface Entity { validate(): boolean; }\nexport class User implements Entity { validate(){ return true; } }\n",
            "server/Base.java": "package server; public class Base {}\n",
            "server/Task.java": "package server; public interface Task { void run(); }\n",
            "server/Main.java": (
                "package server;\nimport server.Base;\nimport server.Task;\n"
                "public class Main extends Base implements Task {\n"
                " public void run(){ Util.work(); }\n}\n"
            ),
            "server/Util.java": "package server; public class Util { public static void work() {} }\n",
            "native/main.c": '#include "helper.h"\nint start(){ return helper(); }\n',
            "native/helper.h": "int helper();\n",
            "native/helper.c": "int helper(){ return 1; }\n",
            "native/widget.cpp": (
                "class Renderable { public: virtual void draw() {} };\n"
                "class Widget : public Renderable { public: void draw() override {} };\n"
            ),
            "native/Widget.cs": "using System; namespace App { public interface IThing {} public class Widget : IThing { public void Run(){ Console.WriteLine(1); } } }\n",
            "cmd/main.go": 'package main\nimport "example.com/devtwin/shared"\nfunc main(){ shared.Run() }\n',
            "shared/run.go": "package shared\nfunc Run() {}\n",
            "go.mod": "module example.com/devtwin\n\ngo 1.22\n",
            "web/package.json": '{"dependencies":{"express":"^1.0.0","react":"^1.0.0"}}',
            "requirements.txt": "fastapi>=0.1\n",
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, content in sources.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            analysis = analyze_repository(root)
            graph = build_graph_data(analysis)
            chunks = build_repository_chunks(root, repository_id="fixture", analysis_result=analysis)
            graph_with_chunks = add_chunks_to_graph(graph, chunks)

        self.assertEqual(
            {"Python", "JavaScript JSX", "JavaScript", "TypeScript", "Java", "C", "C/C++ header", "C++", "C#", "Go"},
            {file_info["language"] for file_info in analysis["files"]},
        )
        self.assertGreater(analysis["import_summary"]["total"], 0)
        self.assertGreater(analysis["import_summary"]["internal"], 0)
        self.assertGreater(analysis["import_summary"]["external"], 0)

        edges = {(edge["source"], edge["relationship"], edge["target"]) for edge in graph["relationships"]}
        self.assertIn(("file:app/main.py", "IMPORTS", "file:app/services/auth.py"), edges)
        self.assertIn(("file:app/services/auth.py", "IMPORTS", "file:app/models/user.py"), edges)
        self.assertIn(("file:web/src/main.jsx", "IMPORTS", "file:web/src/App.jsx"), edges)
        self.assertIn(("file:native/main.c", "IMPORTS", "file:native/helper.h"), edges)
        self.assertIn(("file:cmd/main.go", "IMPORTS", "package:shared:shared"), edges)
        self.assertIn(("file:app/main.py", "IMPORTS", "module:fastapi"), edges)
        self.assertIn(("function:app/main.py:login", "CALLS", "function:app/services/auth.py:authenticate"), edges)
        self.assertIn(("function:cmd/main.go:main", "CALLS", "function:shared/run.go:Run"), edges)
        self.assertIn(("method:server/Main.java:Main.run", "CALLS", "method:server/Util.java:Util.work"), edges)
        self.assertIn(("api:app/main.py:GET:/login", "HANDLED_BY", "function:app/main.py:login_endpoint"), edges)
        self.assertIn(("file:web/src/App.jsx", "EXPORTS", "function:web/src/App.jsx:App"), edges)
        self.assertIn(("project:root", "CONTAINS", "folder:app"), edges)
        self.assertTrue(any(edge[1] == "EXTENDS" for edge in edges))
        self.assertTrue(any(edge[1] == "IMPLEMENTS" for edge in edges))
        self.assertIn(("class:native/widget.cpp:Widget", "EXTENDS", "class:native/widget.cpp:Renderable"), edges)
        self.assertIn(("class:native/Widget.cs:Widget", "IMPLEMENTS", "interface:native/Widget.cs:IThing"), edges)
        self.assertIn(("interface:server/Task.java:Task", "HAS_METHOD", "method:server/Task.java:Task.run"), edges)
        self.assertIn(("interface:web/src/types/user.ts:Entity", "HAS_METHOD", "method:web/src/types/user.ts:Entity.validate"), edges)
        self.assertTrue(any(edge[1] == "CALLS" for edge in edges))
        self.assertTrue(any(node["type"] == "API" and node["name"] == "GET /items" for node in graph["nodes"]))
        self.assertGreater(len(chunks), 0)
        chunk_edges = {(edge["source"], edge["relationship"], edge["target"]) for edge in graph_with_chunks["relationships"]}
        self.assertTrue(any(edge[1] == "HAS_CHUNK" and edge[0].startswith("function:web/src/") for edge in chunk_edges))


if __name__ == "__main__":
    unittest.main()
