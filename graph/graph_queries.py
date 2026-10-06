"""Read-only queries over graph data produced by ``build_graph_data``."""

from collections import deque


def _node_id(graph_data, identifier):
    """Accept a node ID or an unambiguous node name."""

    node_ids = {node["id"] for node in graph_data["nodes"]}
    if identifier in node_ids:
        return identifier

    matches = [
        node["id"]
        for node in graph_data["nodes"]
        if node["name"] == identifier
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise KeyError(f"Graph node not found: {identifier}")
    raise ValueError(f"Graph node name is ambiguous: {identifier}")


def _adjacency(graph_data, reverse=False, relationship_types=None):
    allowed = set(relationship_types) if relationship_types is not None else None
    adjacency = {}
    for edge in graph_data["relationships"]:
        if allowed is not None and edge["relationship"] not in allowed:
            continue
        source, target = edge["source"], edge["target"]
        if reverse:
            source, target = target, source
        adjacency.setdefault(source, []).append((target, edge["relationship"]))
    return adjacency


def find_dependencies(graph_data, identifier, max_depth=1):
    """Return nodes reachable through outgoing relationships up to max_depth."""

    return _traverse(graph_data, identifier, max_depth, reverse=False)


def find_dependents(graph_data, identifier, max_depth=1):
    """Return nodes that reach the selected node through incoming edges."""

    return _traverse(graph_data, identifier, max_depth, reverse=True)


def _traverse(graph_data, identifier, max_depth, reverse):
    if max_depth < 1:
        return []

    start = _node_id(graph_data, identifier)
    adjacency = _adjacency(graph_data, reverse=reverse)
    visited = {start}
    queue = deque([(start, 0)])
    results = []

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for target, relationship in adjacency.get(current, []):
            if target in visited:
                continue
            visited.add(target)
            results.append({
                "id": target,
                "relationship": relationship,
                "depth": depth + 1,
            })
            queue.append((target, depth + 1))

    return results


def find_relationship_path(graph_data, source, target, relationship_types=None):
    """Return the shortest directed relationship path, or an empty list."""

    source_id = _node_id(graph_data, source)
    target_id = _node_id(graph_data, target)
    adjacency = _adjacency(
        graph_data,
        relationship_types=relationship_types,
    )
    queue = deque([source_id])
    previous = {source_id: None}
    previous_edge = {}

    while queue:
        current = queue.popleft()
        if current == target_id:
            break
        for next_id, relationship in adjacency.get(current, []):
            if next_id in previous:
                continue
            previous[next_id] = current
            previous_edge[next_id] = relationship
            queue.append(next_id)

    if target_id not in previous:
        return []

    path = []
    current = target_id
    while current != source_id:
        parent = previous[current]
        path.append({
            "source": parent,
            "relationship": previous_edge[current],
            "target": current,
        })
        current = parent
    path.reverse()
    return path


def find_impact(graph_data, identifier, max_depth=3):
    """Return reverse-reachable nodes as a basic file/import impact view."""

    affected = find_dependents(graph_data, identifier, max_depth=max_depth)
    nodes_by_id = {node["id"]: node for node in graph_data["nodes"]}
    return [
        {**nodes_by_id[item["id"]], "depth": item["depth"]}
        for item in affected
        if item["id"] in nodes_by_id
    ]
