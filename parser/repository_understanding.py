"""Create conservative repository summaries from checked-in evidence."""

import ast
import json
import os
import re
import tomllib
from collections import Counter
from pathlib import Path



LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript (JSX)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (TSX)",
    ".java": "Java",
    ".c": "C",
    ".h": "C/C++ header",
    ".cpp": "C++",
    ".hpp": "C++ header",
    ".cc": "C++",
    ".cxx": "C++",
    ".hxx": "C++ header",
    ".cs": "C#",
    ".go": "Go",
}
README_NAMES = ("README.md", "README.rst", "README.txt", "README")
FRAMEWORK_EVIDENCE = {
    "FastAPI": {"fastapi", "fastapi_users"},
    "Flask": {"flask"},
    "Django": {"django"},
    "React": {"react", "react-dom"},
    "Next.js": {"next"},
    "Vue": {"vue"},
    "Angular": {"@angular/core"},
    "Express": {"express"},
    "NestJS": {"@nestjs/core"},
    "Fastify": {"fastify"},
    "Spring": {"spring-boot", "spring-web", "spring"},
    "Gin": {"github.com/gin-gonic/gin"},
    "Echo": {"github.com/labstack/echo"},
}
FRONTEND_FRAMEWORKS = {"React", "Next.js", "Vue", "Angular"}
BACKEND_FRAMEWORKS = {
    "FastAPI", "Flask", "Django", "Express", "NestJS", "Fastify",
    "Spring", "Gin", "Echo",
}
BUILD_MARKERS = {"npm scripts", "pyproject.toml", "Maven", "Gradle", "Cargo", "Go modules"}


def build_project_understanding(repository_root, analysis, graph_data, chunks):
    """Summarize verifiable repository evidence without guessing semantics."""

    root = Path(repository_root).resolve()
    files = analysis["files"]
    language_counts = Counter(item.get("language") or "Unknown" for item in files)
    languages = [
        {"name": name, "files": count}
        for name, count in sorted(language_counts.items())
        if name != "Unknown"
    ]
    edges = graph_data["relationships"]
    display_nodes = [node for node in graph_data["nodes"] if node["type"] != "CODE_CHUNK"]
    display_node_ids = {node["id"] for node in display_nodes}
    display_edges = [
        edge
        for edge in edges
        if edge["source"] in display_node_ids and edge["target"] in display_node_ids
    ]
    import_edges = [edge for edge in edges if edge["relationship"] == "IMPORTS"]
    import_summary = analysis.get("import_summary", {
        "total": len(import_edges), "internal": 0, "external": 0, "unresolved": len(import_edges),
    })
    incoming = Counter(edge["target"] for edge in import_edges)
    outgoing = Counter(edge["source"] for edge in import_edges)
    connected_files = sorted(
        (
            {
                "file": node["name"],
                "connections": incoming[node["id"]] + outgoing[node["id"]],
            }
            for node in graph_data["nodes"]
            if node["type"] == "FILE"
        ),
        key=lambda item: (-item["connections"], item["file"]),
    )

    folder_counts = Counter(
        Path(item["file"]).parts[0]
        for item in files
        if len(Path(item["file"]).parts) > 1
    )
    folders = [
        {"name": name, "source_files": count}
        for name, count in sorted(folder_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    readme = _repository_documentation(root)
    technologies = _declared_technologies(root)
    entry_points = _entry_points(root, files)
    documented_components = _documented_components(root, files)
    frameworks = _framework_evidence(files, technologies)
    project_type = _project_type(frameworks)
    main_components = _main_components(folders, documented_components)
    architecture_summary = _architecture_summary(entry_points, import_summary)
    dependencies = [technology for technology in technologies if technology not in BUILD_MARKERS]
    purpose = readme["summary"] or "Not enough information available from the analyzed repository."

    return {
        "repository_name": root.name,
        "project_name": root.name,
        "purpose": purpose,
        "summary": purpose,
        "project_type": project_type,
        "project_type_evidence": frameworks if project_type else [],
        "purpose_evidence": readme["file"],
        "documentation_evidence": readme["documents"],
        "analysis_scope": (
            "Tree-sitter structural extraction is enabled for Python, JavaScript, JSX, "
            "TypeScript, TSX, Java, C, C++, C#, and Go. Import, definition, containment, "
            "call, export, inheritance, and API relationships are static evidence; "
            "runtime control flow is not inferred."
        ),
        "architecture_summary": architecture_summary,
        "how_it_works": (
            f"Static analysis found {import_summary['total']} imports: "
            f"{import_summary['internal']} resolved inside this repository, "
            f"{import_summary['external']} identified as external packages, and "
            f"{import_summary['unresolved']} unresolved. Relationships come from parsed "
            "syntax and manifests; runtime control flow is not inferred."
        ),
        "architecture_note": (
            "The graph represents extracted file imports, definitions, methods, and code "
            "chunks. It does not infer service layers or runtime control flow."
        ),
        "technologies": technologies,
        "frameworks": frameworks,
        "dependencies": dependencies,
        "import_analysis": import_summary,
        "languages": languages,
        "main_components": main_components,
        "documented_components": documented_components,
        "folders": folders,
        "directory_summary": folders,
        "entry_points": entry_points,
        "most_connected_files": connected_files[:8],
        "statistics": {
            "files": len(files),
            "classes": sum(len(item["classes"]) for item in files),
            "interfaces": sum(len(item.get("interfaces", [])) for item in files),
            "functions": sum(len(item["functions"]) for item in files),
            "methods": sum(len(item["methods"]) for item in files),
            "apis": sum(len(item.get("api_endpoints", [])) for item in files),
            "calls": sum(edge["relationship"] == "CALLS" for edge in display_edges),
            "modules": len({module for item in files for module in item["imports"]}),
            "graph_nodes": len(display_nodes),
            "relationships": len(display_edges),
            "code_chunks": len(chunks),
        },
        "architecture_edges": [
            {
                "source": edge["source"].removeprefix("file:"),
                "target": edge["target"].removeprefix("file:").removeprefix("module:"),
                "relationship": edge["relationship"],
            }
            for edge in import_edges[:24]
        ],
    }


def _framework_evidence(files, technologies):
    """Report recognized frameworks only when manifests or imports show them."""

    manifest_names = {
        name.strip().lower().replace("_", "-") for name in technologies
    }
    imported_modules = {
        str(module).strip().lower().replace("_", "-")
        for file_info in files
        for module in file_info.get("imports", [])
    }
    for file_info in files:
        for record in file_info.get("import_records", []):
            imported_modules.add(
                str(record.get("module", "")).strip().lower().replace("_", "-")
            )

    evidence = []
    for framework, names in FRAMEWORK_EVIDENCE.items():
        normalized_names = {name.lower().replace("_", "-") for name in names}
        manifest_match = normalized_names & manifest_names
        import_match = {
            imported for imported in imported_modules
            if any(
                imported == name or imported.startswith(name + ".")
                or imported.startswith(name + "/")
                for name in normalized_names
            )
        }
        if manifest_match or import_match:
            sources = []
            if manifest_match:
                sources.append("declared dependency: " + ", ".join(sorted(manifest_match)))
            if import_match:
                sources.append("source import: " + ", ".join(sorted(import_match)))
            evidence.append({"name": framework, "evidence": "; ".join(sources)})
    return evidence


def _project_type(frameworks):
    """Infer a broad application category only from recognized framework evidence."""

    names = {item["name"] for item in frameworks}
    has_frontend = bool(names & FRONTEND_FRAMEWORKS)
    has_backend = bool(names & BACKEND_FRAMEWORKS)
    if has_frontend and has_backend:
        return "Full-stack web application"
    if has_frontend:
        return "Web frontend"
    if has_backend:
        return "Backend web application or API service"
    return None


def _main_components(folders, documented_components):
    """Summarize observed repository areas and attach explicit source docs."""

    components = [
        {
            "name": f"{folder['name']}/",
            "description": f"Contains {folder['source_files']} scanned source files.",
            "evidence": "Repository directory structure",
        }
        for folder in folders[:8]
    ]
    components.extend(
        {
            "name": component["name"],
            "file": component["file"],
            "description": component["purpose"],
            "evidence": "Source documentation or docstring",
        }
        for component in documented_components[:8]
    )
    return components[:12]


def _architecture_summary(entry_points, import_summary):
    """Describe only observed entry-point and static import evidence."""

    entry_files = sorted({item["file"] for item in entry_points})
    parts = []
    if entry_files:
        parts.append("Entry-point evidence was found in " + ", ".join(entry_files[:4]) + ".")
    internal = import_summary.get("internal", 0)
    external = import_summary.get("external", 0)
    unresolved = import_summary.get("unresolved", 0)
    if internal or external or unresolved:
        parts.append(
            f"Static analysis counted {internal} internal, {external} external, "
            f"and {unresolved} unresolved imports."
        )
    if not parts:
        return "Not enough repository evidence to summarize the architecture."
    parts.append("These relationships do not establish runtime execution order.")
    return " ".join(parts)


def summarize_file(repository_root, relative_path, analysis, graph_data):
    """Return concise source facts and documentation for one analyzed file."""

    root = Path(repository_root).resolve()
    relative = Path(relative_path)
    source_path = (root / relative).resolve()
    try:
        source_path.relative_to(root)
    except ValueError as error:
        raise ValueError("File path must stay inside the analyzed repository.") from error
    if not source_path.is_file():
        raise FileNotFoundError("The selected source file was not found.")

    normalized = relative.as_posix()
    file_info = next((item for item in analysis["files"] if item["file"] == normalized), None)
    if file_info is None:
        raise FileNotFoundError("The selected file is not part of the repository analysis.")

    content = source_path.read_text(encoding="utf-8")
    documentation = _source_documentation(content, source_path.suffix.lower())
    documented_components = _file_component_documentation(content) if source_path.suffix.lower() == ".py" else []
    file_id = f"file:{normalized}"
    nodes = {node["id"]: node for node in graph_data["nodes"]}
    dependencies = [
        _friendly_node(nodes.get(edge["target"], {"name": edge["target"]}))
        for edge in graph_data["relationships"]
        if edge["source"] == file_id and edge["relationship"] == "IMPORTS"
    ]
    used_by = [
        _friendly_node(nodes.get(edge["source"], {"name": edge["source"]}))
        for edge in graph_data["relationships"]
        if edge["target"] == file_id and edge["relationship"] == "IMPORTS"
    ]
    api_endpoints = [
        {"method": endpoint["method"], "path": endpoint["path"], "handler": endpoint.get("handler")}
        for endpoint in file_info.get("api_endpoints", [])
    ]
    calls = [
        f"{nodes[edge['source']]['name']} → {nodes[edge['target']]['name']}"
        for edge in graph_data["relationships"]
        if edge["relationship"] == "CALLS"
        and edge["source"] in nodes
        and edge["target"] in nodes
        and nodes[edge["source"]].get("file") == normalized
    ]
    call_expressions = [
        f"{call['caller']} → {call['callee']}"
        for call in file_info.get("calls", [])
    ]
    return {
        "file": normalized,
        "language": file_info.get("language", LANGUAGES.get(source_path.suffix.lower(), "Unknown")),
        "purpose": documentation or _structural_file_explanation(file_info),
        "documentation": documentation,
        "documented_components": documented_components,
        "classes": file_info["classes"],
        "functions": file_info["functions"],
        "methods": file_info["methods"],
        "interfaces": file_info.get("interfaces", []),
        "exports": file_info.get("exports", []),
        "api_endpoints": api_endpoints,
        "calls": calls,
        "call_expressions": call_expressions,
        "imports": file_info["imports"],
        "dependencies": dependencies,
        "used_by": sorted(set(used_by)),
        "source_lines": len(content.splitlines()),
        "explanation_basis": (
            "Source documentation when present; otherwise a concise summary of parsed declarations, "
            "imports, exports, API routes, and static relationships. No generated LLM explanation."
        ),
    }


def _source_documentation(content, suffix):
    if suffix == ".py":
        return _python_documentation(content)
    # Read a leading file comment as documentation only when it is explicit.
    lines = content.splitlines()
    comment_prefixes = {".js": "//", ".jsx": "//", ".ts": "//", ".tsx": "//", ".java": "//", ".c": "//", ".cpp": "//", ".cs": "//", ".go": "//"}
    prefix = comment_prefixes.get(suffix)
    if not prefix:
        return None
    comments = []
    for line in lines[:30]:
        stripped = line.strip()
        if not stripped:
            if comments:
                break
            continue
        if stripped.startswith(prefix):
            comments.append(stripped[len(prefix):].strip(" */"))
        else:
            break
    return " ".join(item for item in comments if item)[:600] or None


def _structural_file_explanation(file_info):
    """Summarize parsed facts without guessing what their business purpose is."""

    facts = []
    definitions = []
    definitions.extend(f"class {name}" for name in file_info.get("classes", []))
    definitions.extend(f"interface {name}" for name in file_info.get("interfaces", []))
    definitions.extend(f"function {name}" for name in file_info.get("functions", []))
    definitions.extend(f"method {name}" for name in file_info.get("methods", []))
    if definitions:
        facts.append("Defines " + ", ".join(definitions[:8]) + (" and more" if len(definitions) > 8 else ""))
    if file_info.get("api_endpoints"):
        endpoints = [f"{item['method']} {item['path']}" for item in file_info["api_endpoints"][:6]]
        facts.append("declares API endpoint(s) " + ", ".join(endpoints))
    if file_info.get("exports"):
        facts.append("exports " + ", ".join(file_info["exports"][:8]))
    if file_info.get("imports"):
        facts.append("imports " + ", ".join(file_info["imports"][:8]))
    if facts:
        return (
            "Not enough information available to infer business purpose confidently. "
            "Parsed structure: " + "; ".join(facts) + "."
        )
    return "Not enough information available from this file's comments or parsed structure to explain it confidently."


def _repository_documentation(root):
    candidates = [root / name for name in README_NAMES]
    documents = []
    summary = None
    evidence_file = None
    for path in candidates:
        if not path.is_file():
            continue
        summary = _first_document_paragraph(path.read_text(encoding="utf-8", errors="replace"))
        if summary:
            evidence_file = path.relative_to(root).as_posix()
            break

    if not summary:
        package_path = root / "package.json"
        if package_path.is_file():
            try:
                package_description = json.loads(package_path.read_text(encoding="utf-8")).get("description")
                if isinstance(package_description, str) and package_description.strip():
                    summary = package_description.strip()
                    evidence_file = "package.json · description"
            except (OSError, json.JSONDecodeError):
                pass
        project_path = root / "pyproject.toml"
        if not summary and project_path.is_file():
            try:
                description = tomllib.loads(project_path.read_text(encoding="utf-8")).get("project", {}).get("description")
                if isinstance(description, str) and description.strip():
                    summary = description.strip()
                    evidence_file = "pyproject.toml · project.description"
            except (OSError, tomllib.TOMLDecodeError):
                pass

    documentation_dir = root / "docs"
    if documentation_dir.is_dir():
        for path in sorted(documentation_dir.glob("*.md"))[:8]:
            excerpt = _first_document_paragraph(path.read_text(encoding="utf-8", errors="replace"))
            if excerpt:
                documents.append({"file": path.relative_to(root).as_posix(), "excerpt": excerpt})
    return {"file": evidence_file, "summary": summary, "documents": documents}


def _first_document_paragraph(text):
    lines = []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip() or line.lstrip().startswith("#"):
            if lines:
                break
            continue
        cleaned = re.sub(r"!?(\[[^\]]*\])\([^)]*\)", r"\1", line.strip())
        cleaned = re.sub(r"[`*_]", "", cleaned)
        lines.append(cleaned)
        if len(" ".join(lines)) > 500 or len(lines) >= 3:
            break
    return " ".join(lines).strip()[:600]


def _declared_technologies(root):
    found = set()
    package_paths = _manifest_paths(root, "package.json")
    for package_path in package_paths:
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            for group in ("dependencies", "devDependencies"):
                found.update(package.get(group, {}).keys())
            if package.get("scripts"):
                found.add("npm scripts")
        except (OSError, json.JSONDecodeError):
            pass

    for path in _manifest_paths(root, "requirements.txt") + _manifest_paths(root, "requirements-dev.txt"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-", ".")):
                continue
            match = re.match(r"([A-Za-z0-9_.-]+)", line)
            if match:
                found.add(match.group(1))
    for path in _manifest_paths(root, "pyproject.toml"):
        found.add("pyproject.toml")
        try:
            project = tomllib.loads(path.read_text(encoding="utf-8"))
            for dependency in project.get("project", {}).get("dependencies", []):
                match = re.match(r"([A-Za-z0-9_.-]+)", dependency)
                if match:
                    found.add(match.group(1))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    for marker, tool_name in (("pom.xml", "Maven"), ("Cargo.toml", "Cargo"), ("go.mod", "Go modules"), ("build.gradle", "Gradle"), ("build.gradle.kts", "Gradle")):
        if _manifest_paths(root, marker):
            found.add(tool_name)
    return sorted(found)


def _entry_points(root, files):
    result = []
    for package_path in _manifest_paths(root, "package.json"):
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            for name, command in package.get("scripts", {}).items():
                relative_manifest = package_path.relative_to(root).as_posix()
                result.append({"file": relative_manifest, "name": f"npm run {name}", "evidence": command})
            for field in ("main", "module", "bin"):
                target = package.get(field)
                if isinstance(target, str):
                    result.append({"file": package_path.relative_to(root).as_posix(), "name": field, "evidence": target})
        except (OSError, json.JSONDecodeError):
            pass

    for html_path in _manifest_paths(root, "index.html"):
        try:
            html = html_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.search(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", html, re.IGNORECASE)
        if match:
            script_path = match.group(1).lstrip("/")
            if (html_path.parent / script_path).is_file():
                result.append({
                    "file": html_path.relative_to(root).as_posix(),
                    "name": "HTML module bootstrap",
                    "evidence": script_path,
                })

    for item in files:
        for entry in item.get("entry_points", []):
            result.append({
                "file": item["file"], "name": entry["name"],
                "evidence": entry["evidence"],
            })
        if Path(item["file"]).suffix.lower() != ".py":
            continue
        if Path(item["file"]).stem.startswith("test_") or "tests" in Path(item["file"]).parts:
            continue
        path = root / item["file"]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call_name = node.value.func.id if isinstance(node.value.func, ast.Name) else None
                if call_name == "FastAPI":
                    names = [target.id for target in node.targets if isinstance(target, ast.Name)]
                    if names:
                        result.append({
                            "file": item["file"],
                            "name": f"FastAPI application ({', '.join(names)})",
                            "evidence": "assigned from FastAPI()",
                        })
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
            ):
                result.append({"file": item["file"], "name": "Python __main__ guard", "evidence": "if __name__ == '__main__'"})
                break
    return result


def _manifest_paths(root, filename):
    ignored = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
    found = []
    for current, directories, files in os.walk(root):
        relative_dir = Path(current).relative_to(root)
        directories[:] = [
            name for name in directories
            if name not in ignored and len(relative_dir.parts) < 6
        ]
        if filename in files:
            found.append(Path(current) / filename)
    return sorted(found)


def _documented_components(root, files):
    components = []
    for item in files:
        if Path(item["file"]).suffix.lower() != ".py":
            continue
        try:
            source = (root / item["file"]).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        module_doc = _python_documentation(source)
        if module_doc:
            components.append({"file": item["file"], "name": "Module", "purpose": module_doc})
        for documented in _file_component_documentation(source):
            components.append({"file": item["file"], **documented})
        if len(components) >= 24:
            return components[:24]
    return components[:24]


def _file_component_documentation(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    result = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=True)
            if doc:
                result.append({
                    "name": node.name,
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "purpose": doc,
                })
    return result


def _python_documentation(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    return ast.get_docstring(tree, clean=True)


def _friendly_node(node):
    if node.get("type") == "FILE":
        return node.get("file") or node.get("name")
    return node.get("name") or node.get("id")
