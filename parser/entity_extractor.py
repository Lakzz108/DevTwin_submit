from tree_sitter import Node

from code_parser import parse_python_file


def get_node_text(node: Node) -> str:
    """Return the source text represented by a Tree-sitter node."""

    if node is None:
        return ""

    return node.text.decode("utf-8")


def normalize_import(node: Node) -> str:
    """
    Convert a Python import statement into a simple module name.

    Examples:
        import sys
            -> sys

        import tree_sitter_python
            -> tree_sitter_python

        from pathlib import Path
            -> pathlib

        from code_parser import parse_python_file
            -> code_parser
    """

    import_text = get_node_text(node).strip()

    if node.type == "import_statement":

        import_text = import_text.replace("import ", "", 1).strip()

        # Handle aliases such as:
        # import numpy as np
        if " as " in import_text:
            import_text = import_text.split(" as ")[0].strip()

        return import_text

    if node.type == "import_from_statement":

        import_text = import_text.replace("from ", "", 1).strip()

        # Everything before " import " is the module.
        if " import " in import_text:
            import_text = import_text.split(" import ", 1)[0].strip()

        return import_text

    return import_text


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

    def visit(node: Node, current_class=None, inside_function=False):

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

                # Function inside a class = method
                if current_class and not inside_function:

                    method_name = f"{current_class}.{function_name}"

                    entities["methods"].append(method_name)

                    relationships.append({
                        "source": current_class,
                        "relationship": "HAS_METHOD",
                        "target": method_name,
                    })

                # Top-level function
                elif not inside_function:

                    entities["functions"].append(function_name)

                    relationships.append({
                        "source": file_path,
                        "relationship": "DEFINES",
                        "target": function_name,
                    })

                # Nested function
                # Do not add it as a top-level entity.

                inside_function = True

        # Imports
        elif node.type in {
            "import_statement",
            "import_from_statement",
        }:

            import_target = normalize_import(node)

            if import_target:
                entities["imports"].append(import_target)

                relationships.append({
                    "source": file_path,
                    "relationship": "IMPORTS",
                    "target": import_target,
                })

        # Visit children
        for child in node.children:
            visit(child, current_class, inside_function)

    visit(tree.root_node)

    return {
        "entities": entities,
        "relationships": relationships,
    }