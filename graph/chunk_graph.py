"""Attach source-code chunks to repository graph data."""


def add_chunks_to_graph(graph_data, chunks):
    """Add CODE_CHUNK nodes linked to their file and, when known, symbol."""

    result = {
        "nodes": [dict(node) for node in graph_data["nodes"]],
        "relationships": [dict(edge) for edge in graph_data["relationships"]],
    }
    existing_nodes = {node["id"] for node in result["nodes"]}
    existing_edges = {
        (edge["source"], edge["relationship"], edge["target"])
        for edge in result["relationships"]
    }

    for chunk in chunks:
        chunk_id = chunk["id"]
        if chunk_id in existing_nodes:
            continue

        symbol_kind = chunk["kind"]
        symbol = chunk.get("symbol")
        node = {
            "id": chunk_id,
            "type": "CODE_CHUNK",
            "name": symbol or chunk["file"],
            "file": chunk["file"],
            "symbol_kind": symbol_kind,
            "symbol": symbol,
            "class_name": chunk.get("class_name"),
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "content": chunk["content"],
        }
        if "repository_id" in chunk:
            node["repository_id"] = chunk["repository_id"]
        result["nodes"].append(node)
        existing_nodes.add(chunk_id)

        file_id = f"file:{chunk['file']}"
        edges_to_add = [(file_id, "CONTAINS_CHUNK", chunk_id)]

        symbol_node_id = _symbol_node_id(chunk)
        if symbol_node_id and symbol_node_id in existing_nodes:
            edges_to_add.append((chunk_id, "DESCRIBES", symbol_node_id))

        for source, relationship, target in edges_to_add:
            edge_key = (source, relationship, target)
            if edge_key not in existing_edges:
                result["relationships"].append({
                    "source": source,
                    "relationship": relationship,
                    "target": target,
                })
                existing_edges.add(edge_key)

    return result


def _symbol_node_id(chunk):
    kind = chunk["kind"]
    file_path = chunk["file"]
    symbol = chunk.get("symbol")
    if not symbol:
        return None
    if kind == "CLASS":
        return f"class:{file_path}:{symbol}"
    if kind == "METHOD":
        return f"method:{file_path}:{symbol}"
    if kind == "FUNCTION":
        return f"function:{file_path}:{symbol}"
    return None
