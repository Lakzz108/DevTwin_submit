"""Build a repository-scoped knowledge graph from normalized source facts."""

from collections import defaultdict
from pathlib import Path


def build_graph_data(analysis_result):
    """Create project, folder, file, symbol and dependency graph records."""

    nodes = []
    relationships = []
    node_ids = set()
    edge_ids = set()
    symbol_ids = {}
    symbols_by_name = defaultdict(list)
    file_names = {item["file"] for item in analysis_result["files"]}

    def add_node(node_id, node_type, name, **properties):
        if node_id in node_ids:
            return
        node = {"id": node_id, "type": node_type, "name": name}
        node.update({key: value for key, value in properties.items() if value is not None})
        nodes.append(node)
        node_ids.add(node_id)

    def add_edge(source, relationship, target):
        if source not in node_ids or target not in node_ids:
            return
        key = (source, relationship, target)
        if key not in edge_ids:
            relationships.append({"source": source, "relationship": relationship, "target": target})
            edge_ids.add(key)

    project_id = "project:root"
    add_node(project_id, "PROJECT", analysis_result.get("repository_name", "Repository"))

    # Build the repository's real directory hierarchy.
    folder_paths = set()
    for file_info in analysis_result["files"]:
        parent = Path(file_info["file"]).parent
        while parent.as_posix() not in {".", ""}:
            folder_paths.add(parent.as_posix())
            parent = parent.parent
    for folder_path in sorted(folder_paths, key=lambda item: (item.count("/"), item)):
        add_node(f"folder:{folder_path}", "FOLDER", Path(folder_path).name, path=folder_path)
        parent = Path(folder_path).parent.as_posix()
        parent_id = f"folder:{parent}" if parent not in {".", ""} else project_id
        add_edge(parent_id, "CONTAINS", f"folder:{folder_path}")

    for file_info in analysis_result["files"]:
        file_path = file_info["file"]
        file_id = f"file:{file_path}"
        add_node(
            file_id, "FILE", file_path, file=file_path,
            language=file_info.get("language"), parse_error=file_info.get("parse_error"),
        )
        parent = Path(file_path).parent.as_posix()
        parent_id = f"folder:{parent}" if parent not in {".", ""} else project_id
        add_edge(parent_id, "CONTAINS", file_id)

        if file_info.get("package"):
            package_id = _package_id(file_info)
            add_node(package_id, "PACKAGE", file_info["package"], path=parent, language=file_info.get("language"))
            add_edge(package_id, "CONTAINS", file_id)

        symbol_details = file_info.get("symbols") or _fallback_symbols(file_info)
        for symbol in symbol_details:
            kind = symbol["type"]
            name = symbol["name"]
            qualified = symbol.get("qualified_name", name)
            symbol_id = _symbol_id(file_path, kind, qualified)
            add_node(
                symbol_id, kind, qualified, file=file_path,
                language=file_info.get("language"), start_line=symbol.get("start_line"),
                end_line=symbol.get("end_line"),
            )
            symbol_ids[(file_path, kind, qualified)] = symbol_id
            if symbol_id not in symbols_by_name[name]:
                symbols_by_name[name].append(symbol_id)
            if symbol_id not in symbols_by_name[qualified]:
                symbols_by_name[qualified].append(symbol_id)
            if kind == "METHOD":
                class_name = qualified.rsplit(".", 1)[0] if "." in qualified else None
                class_id = (
                    symbol_ids.get((file_path, "CLASS", class_name))
                    or symbol_ids.get((file_path, "INTERFACE", class_name))
                )
                if class_id:
                    add_edge(class_id, "HAS_METHOD", symbol_id)
            else:
                add_edge(file_id, "DEFINES", symbol_id)

        # A Python class may appear after a method in AST traversal order only
        # if the grammar contains unusual nested declarations, so link methods
        # after all symbols in the file are indexed as well.
        for symbol in symbol_details:
            if symbol["type"] == "METHOD":
                qualified = symbol.get("qualified_name", symbol["name"])
                class_name = qualified.rsplit(".", 1)[0] if "." in qualified else None
                class_id = (
                    symbol_ids.get((file_path, "CLASS", class_name))
                    or symbol_ids.get((file_path, "INTERFACE", class_name))
                )
                method_id = symbol_ids.get((file_path, "METHOD", qualified))
                if class_id and method_id:
                    add_edge(class_id, "HAS_METHOD", method_id)

    module_ids = {}
    node_by_id = {node["id"]: node for node in nodes}
    for file_info in analysis_result["files"]:
        file_path = file_info["file"]
        file_id = f"file:{file_path}"
        records = file_info.get("import_records")
        if records is None:
            records = [{"module": name, "resolution": "unresolved"} for name in file_info.get("imports", [])]
        for record in records:
            if record.get("resolution") == "internal" and record.get("target_file") in file_names:
                add_edge(file_id, "IMPORTS", f"file:{record['target_file']}")
            elif record.get("resolution") == "internal" and record.get("target_package"):
                package_id = f"package:{record['target_package']}:{record.get('target_package_name', Path(record['target_package']).name)}"
                add_node(package_id, "PACKAGE", record.get("target_package_name", Path(record["target_package"]).name), path=record["target_package"])
                add_edge(file_id, "IMPORTS", package_id)
            else:
                module = record["module"]
                module_id = f"module:{module}"
                add_node(
                    module_id, "MODULE", module,
                    resolution=record.get("resolution", "unresolved"),
                    language=file_info.get("language"),
                )
                module_ids[module] = module_id
                add_edge(file_id, "IMPORTS", module_id)

        for exported_name in file_info.get("exports", []):
            candidates = _symbols_for_file(symbol_ids, file_path, exported_name)
            if len(candidates) == 1:
                add_edge(file_id, "EXPORTS", candidates[0])

        for inheritance in file_info.get("inheritance", []):
            child_ids = _symbols_for_file(symbol_ids, file_path, inheritance["child"])
            parent_ids = symbols_by_name.get(inheritance["parent"], [])
            if len(child_ids) == 1 and len(parent_ids) == 1:
                relationship = inheritance["relationship"]
                # C# uses one base-list syntax for both a base class and
                # implemented interfaces. The parsed target declaration tells
                # us which relationship is supported by repository evidence.
                if node_by_id.get(parent_ids[0], {}).get("type") == "INTERFACE":
                    relationship = "IMPLEMENTS"
                add_edge(child_ids[0], relationship, parent_ids[0])

        for call in file_info.get("calls", []):
            caller_ids = _symbols_for_file(symbol_ids, file_path, call["caller"])
            if len(caller_ids) != 1:
                continue
            candidates = symbols_by_name.get(call["callee"], [])
            receiver = call.get("receiver")
            if receiver in {"self", "this"} and "." in call["caller"]:
                class_name = call["caller"].rsplit(".", 1)[0]
                candidates = _symbols_for_file(symbol_ids, file_path, f"{class_name}.{call['callee']}")
            elif receiver:
                # Resolve an explicit class receiver (Class.method) or a
                # package/module alias that imports the target file. Ordinary
                # variable receiver types remain unknown and are not guessed.
                qualified = symbols_by_name.get(f"{receiver}.{call['callee']}", [])
                if len(qualified) == 1:
                    candidates = qualified
                else:
                    imported_files = set()
                    imported_packages = set()
                    for record in records:
                        alias = record.get("alias") or Path(record["module"].rstrip("/")).name
                        if alias != receiver:
                            continue
                        if record.get("target_file"):
                            imported_files.add(record["target_file"])
                        if record.get("target_package"):
                            imported_packages.add(record["target_package"])
                    candidates = [
                        identifier for identifier in symbols_by_name.get(call["callee"], [])
                        if node_by_id.get(identifier, {}).get("file") in imported_files
                        or Path(node_by_id.get(identifier, {}).get("file", "")).parent.as_posix() in imported_packages
                    ]
            if len(candidates) == 1:
                add_edge(caller_ids[0], "CALLS", candidates[0])

        for endpoint in file_info.get("api_endpoints", []):
            api_id = f"api:{file_path}:{endpoint['method']}:{endpoint['path']}"
            add_node(
                api_id, "API", f"{endpoint['method']} {endpoint['path']}",
                file=file_path, method=endpoint["method"], path=endpoint["path"],
                handler=endpoint.get("handler"), language=file_info.get("language"),
                start_line=endpoint.get("line"),
            )
            handler = endpoint.get("handler", "")
            handler_ids = _symbols_for_file(symbol_ids, file_path, handler)
            add_edge(api_id, "HANDLED_BY", handler_ids[0]) if len(handler_ids) == 1 else None

    return {"nodes": nodes, "relationships": relationships}


def _fallback_symbols(file_info):
    result = []
    for kind, key in (("CLASS", "classes"), ("INTERFACE", "interfaces"), ("FUNCTION", "functions"), ("METHOD", "methods")):
        for name in file_info.get(key, []):
            result.append({"type": kind, "name": name, "qualified_name": name})
    return result


def _symbol_id(file_path, kind, qualified):
    prefix = {"CLASS": "class", "INTERFACE": "interface", "FUNCTION": "function", "METHOD": "method"}[kind]
    return f"{prefix}:{file_path}:{qualified}"


def _symbols_for_file(symbol_ids, file_path, name):
    if not name:
        return []
    exact = []
    for (source_file, _, qualified), identifier in symbol_ids.items():
        if source_file == file_path and (qualified == name or qualified.rsplit(".", 1)[-1] == name):
            exact.append(identifier)
    return list(dict.fromkeys(exact))


def _package_id(file_info):
    parent = Path(file_info["file"]).parent.as_posix()
    return f"package:{parent}:{file_info['package']}"
