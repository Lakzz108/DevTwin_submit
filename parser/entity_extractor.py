from tree_sitter import Node

from code_parser import parse_python_file


def get_node_text(node: Node) -> str:
    """Return the source text represented by a Tree-sitter node."""

    if node is None:
        return ""

    return node.text.decode("utf-8")


def extract_entities(file_path: str):
    """
    Extract entities and relationships from a Python source file.
    """

    tree = parse_python_file(file_path)

    entities = {
        "file": file_path,
        "classes": [],
        "functions": [],
        "methods": [],
        "imports": [],
    }

    relationships = []

    def visit(node: Node, current_class=None):

        # Class
        if node.type == "class_definition":
            class_name = get_node_text(
                node.child_by_field_name("name")
            )

            if class_name:
                entities["classes"].append(class_name)

                relationships.append({
                    "source": file_path,
                    "relationship": "DEFINES",
                    "target": class_name,
                })

            current_class = class_name

        # Function / Method
        elif node.type == "function_definition":
            function_name = get_node_text(
                node.child_by_field_name("name")
            )

            if function_name:
                if current_class:
                    method_name = f"{current_class}.{function_name}"

                    entities["methods"].append(method_name)

                    relationships.append({
                        "source": current_class,
                        "relationship": "HAS_METHOD",
                        "target": method_name,
                    })

                else:
                    entities["functions"].append(function_name)

                    relationships.append({
                        "source": file_path,
                        "relationship": "DEFINES",
                        "target": function_name,
                    })

        # Imports
        elif node.type in {
            "import_statement",
            "import_from_statement",
        }:
            import_name = get_node_text(node)

            entities["imports"].append(import_name)

            relationships.append({
                "source": file_path,
                "relationship": "IMPORTS",
                "target": import_name,
            })

        # Visit child nodes
        for child in node.children:
            visit(child, current_class)

    visit(tree.root_node)

    return {
        "entities": entities,
        "relationships": relationships,
    }