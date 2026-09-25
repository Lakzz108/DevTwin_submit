from tree_sitter import Node

from code_parser import parse_python_file


def extract_entities(file_path: str):
    """
    Extract basic entities from a Python source file.
    """

    tree = parse_python_file(file_path)

    entities = {
        "file": file_path,
        "classes": [],
        "functions": [],
        "methods": [],
        "imports": [],
    }

    def visit(node: Node, current_class=None):

        if node.type == "class_definition":
            class_name = get_node_text(node.child_by_field_name("name"))

            if class_name:
                entities["classes"].append(class_name)

            current_class = class_name

        elif node.type == "function_definition":
            function_name = get_node_text(
                node.child_by_field_name("name")
            )

            if function_name:
                if current_class:
                    entities["methods"].append(
                        f"{current_class}.{function_name}"
                    )
                else:
                    entities["functions"].append(function_name)

        elif node.type == "import_statement":
            entities["imports"].append(
                get_node_text(node)
            )

        elif node.type == "import_from_statement":
            entities["imports"].append(
                get_node_text(node)
            )

        for child in node.children:
            visit(child, current_class)

    def get_node_text(node):
        if node is None:
            return ""

        return node.text.decode("utf-8")

    visit(tree.root_node)

    return entities