from tree_sitter import Language, Parser
import tree_sitter_python


PYTHON_LANGUAGE = Language(tree_sitter_python.language())

parser = Parser(PYTHON_LANGUAGE)


def parse_python_file(file_path: str):
    """
    Parse a Python source file using Tree-sitter.
    """

    with open(file_path, "r", encoding="utf-8") as file:
        source_code = file.read()

    source_bytes = source_code.encode("utf-8")

    tree = parser.parse(source_bytes)

    return tree


def print_tree(node, source_code: bytes, level=0):
    """
    Print the Tree-sitter syntax tree.
    """

    indentation = "  " * level

    node_text = source_code[node.start_byte:node.end_byte].decode(
        "utf-8",
        errors="replace"
    )

    print(f"{indentation}{node.type}: {node_text[:80]}")

    for child in node.children:
        print_tree(child, source_code, level + 1)