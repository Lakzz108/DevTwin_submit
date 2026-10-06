from pathlib import Path


def build_graph_data(analysis_result):
    """
    Convert repository analysis results into graph-ready
    nodes and relationships.

    The output will later be used to create the
    Neo4j knowledge graph.
    """

    nodes = []
    relationships = []

    node_ids = set()

    # Build a conservative lookup from Python module names to analyzed files.
    # A basename such as "utils" is only usable when it identifies one file.
    module_to_files = {}
    for file_info in analysis_result["files"]:
        file_path = Path(file_info["file"])
        module_names = {file_path.stem}
        if file_path.name == "__init__.py":
            module_names.add(file_path.parent.name)
        else:
            module_names.add(".".join(file_path.with_suffix("").parts))

        for module_name in module_names:
            module_to_files.setdefault(module_name, set()).add(file_info["file"])

    def add_node(node_id, node_type, name, file=None):
        """
        Add a node only if it does not already exist.
        """

        if node_id in node_ids:
            return

        node = {
            "id": node_id,
            "type": node_type,
            "name": name,
        }

        if file:
            node["file"] = file

        nodes.append(node)
        node_ids.add(node_id)

    def add_relationship(source, relationship_type, target):
        """
        Add a relationship between two nodes.
        """

        relationships.append({
            "source": source,
            "relationship": relationship_type,
            "target": target,
        })

    # Process every analyzed file
    for file_info in analysis_result["files"]:

        file_path = file_info["file"]

        # FILE NODE
        file_id = f"file:{file_path}"

        add_node(
            node_id=file_id,
            node_type="FILE",
            name=file_path,
        )

        # CLASS NODES
        for class_name in file_info["classes"]:

            class_id = f"class:{file_path}:{class_name}"

            add_node(
                node_id=class_id,
                node_type="CLASS",
                name=class_name,
                file=file_path,
            )

            add_relationship(
                source=file_id,
                relationship_type="DEFINES",
                target=class_id,
            )

        # FUNCTION NODES
        for function_name in file_info["functions"]:

            function_id = f"function:{file_path}:{function_name}"

            add_node(
                node_id=function_id,
                node_type="FUNCTION",
                name=function_name,
                file=file_path,
            )

            add_relationship(
                source=file_id,
                relationship_type="DEFINES",
                target=function_id,
            )

        # METHOD NODES
        for method_name in file_info["methods"]:

            class_name, method_name_only = method_name.split(
                ".",
                1
            )

            class_id = f"class:{file_path}:{class_name}"
            method_id = f"method:{file_path}:{method_name}"

            add_node(
                node_id=method_id,
                node_type="METHOD",
                name=method_name,
                file=file_path,
            )

            add_relationship(
                source=class_id,
                relationship_type="HAS_METHOD",
                target=method_id,
            )

        # IMPORT NODES
        for import_name in file_info["imports"]:

            matching_files = module_to_files.get(import_name, set())

            if len(matching_files) == 1:
                imported_file = next(iter(matching_files))
                import_id = f"file:{imported_file}"
            else:
                import_id = f"module:{import_name}"
                add_node(
                    node_id=import_id,
                    node_type="MODULE",
                    name=import_name,
                )

            add_relationship(
                source=file_id,
                relationship_type="IMPORTS",
                target=import_id,
            )

    return {
        "nodes": nodes,
        "relationships": relationships,
    }
