from tree_sitter import Language, Parser
import tree_sitter_python

from language_detector import detect_language


PYTHON_LANGUAGE = Language(tree_sitter_python.language())


def _get_language_grammar(language_name):
    """Load one of the explicitly supported Tree-sitter grammars."""

    if language_name == "python":
        return PYTHON_LANGUAGE

    if language_name == "javascript":
        import tree_sitter_javascript

        return Language(tree_sitter_javascript.language())

    if language_name == "typescript":
        import tree_sitter_typescript

        # TSX is selected from the file extension in parse_source_file.
        return Language(tree_sitter_typescript.language_typescript())

    grammar_modules = {
        "java": "tree_sitter_java",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "go": "tree_sitter_go",
    }
    if language_name not in grammar_modules:
        raise ValueError(f"Unsupported source language: {language_name}")

    module_name = grammar_modules[language_name]
    module = __import__(module_name)
    return Language(module.language())


def parse_source_file(file_path: str):
    """Parse a supported source file and return ``(language, tree)``."""

    language_name = detect_language(file_path)
    if language_name is None:
        raise ValueError(f"Unsupported source file extension: {file_path}")

    if language_name == "typescript" and str(file_path).lower().endswith(".tsx"):
        import tree_sitter_typescript

        grammar = Language(tree_sitter_typescript.language_tsx())
    else:
        grammar = _get_language_grammar(language_name)

    with open(file_path, "r", encoding="utf-8") as source_file:
        source_bytes = source_file.read().encode("utf-8")

    return language_name, Parser(grammar).parse(source_bytes)


def parse_python_file(file_path: str):
    """
    Parse a Python source file using Tree-sitter.
    """

    # Parser is mutable native state. Create one per parse so concurrent API
    # requests cannot call into the same Tree-sitter parser instance.
    parser = Parser(PYTHON_LANGUAGE)

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
