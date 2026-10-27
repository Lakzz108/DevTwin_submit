"""Conservative common entity extraction for non-Python Tree-sitter trees."""

from tree_sitter import Node


CLASS_NODE_TYPES = {
    "class_declaration",
    "class_specifier",
    "interface_declaration",
    "enum_declaration",
    "struct_specifier",
}
FUNCTION_NODE_TYPES = {
    "function_declaration",
    "function_definition",
    "generator_function_declaration",
}
METHOD_NODE_TYPES = {
    "method_declaration",
    "method_definition",
    "constructor_declaration",
}


def _text(node):
    return node.text.decode("utf-8") if node is not None else ""


def _name(node):
    name = node.child_by_field_name("name")
    if name is not None:
        return _text(name)

    # C/C++ function names are nested below a declarator node.
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        for child in _walk(declarator):
            if child.type in {"identifier", "field_identifier"}:
                return _text(child)

    # C/C++ grammar versions expose class names as type identifiers.
    for child in node.children:
        if child.type in {"type_identifier", "identifier"}:
            return _text(child)
    return ""


def _go_type_spec(node):
    if node.type != "type_spec":
        return ""
    type_node = node.child_by_field_name("type")
    if type_node is not None and type_node.type in {"struct_type", "interface_type"}:
        return _name(node)
    return ""


def _import_names(node, language):
    if language in {"javascript", "typescript"}:
        source = node.child_by_field_name("source")
        value = _text(source).strip("\"'")
        return [value] if value else []

    if language == "java":
        value = _text(node).strip().removeprefix("import ").removesuffix(";")
        value = value.removeprefix("static ").strip()
        return [value] if value else []

    if language == "go":
        return [
            child.text.decode("utf-8").strip('"`')
            for child in _walk(node)
            if child.type == "interpreted_string_literal"
            or child.type == "raw_string_literal"
        ]

    if language in {"c", "cpp"} and node.type == "preproc_include":
        path = node.child_by_field_name("path")
        value = _text(path).strip('<" >')
        return [value] if value else []

    return []


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _go_receiver_type(node):
    receiver = node.child_by_field_name("receiver")
    if receiver is None:
        return ""
    identifiers = [
        _text(child) for child in _walk(receiver)
        if child.type == "type_identifier"
    ]
    return identifiers[-1].lstrip("*") if identifiers else ""


def extract_tree_entities(file_path, language, tree):
    """Map common grammar constructs to DevTwin's existing entity schema."""

    entities = {
        "file": str(file_path),
        "language": language,
        "classes": [],
        "functions": [],
        "methods": [],
        "imports": [],
    }
    relationships = []

    def add_class(name):
        if name and name not in entities["classes"]:
            entities["classes"].append(name)
            relationships.append({
                "source": str(file_path),
                "relationship": "DEFINES",
                "target": name,
            })

    def visit(node, current_class=None, inside_function=False):
        class_name = _go_type_spec(node) or (
            _name(node) if node.type in CLASS_NODE_TYPES else ""
        )
        if class_name:
            add_class(class_name)
            current_class = class_name

        if node.type in {"import_statement", "import_declaration", "preproc_include"}:
            for import_name in _import_names(node, language):
                if import_name:
                    entities["imports"].append(import_name)
                    relationships.append({
                        "source": str(file_path),
                        "relationship": "IMPORTS",
                        "target": import_name,
                    })

        function_name = _name(node) if node.type in FUNCTION_NODE_TYPES else ""
        method_name = _name(node) if node.type in METHOD_NODE_TYPES else ""
        if language == "go" and node.type == "method_declaration":
            owner = _go_receiver_type(node)
            method_name = f"{owner}.{method_name}" if owner else method_name

        if method_name and not inside_function:
            if current_class and "." not in method_name:
                method_name = f"{current_class}.{method_name}"
            if method_name not in entities["methods"]:
                entities["methods"].append(method_name)
                owner = method_name.rsplit(".", 1)[0] if "." in method_name else current_class
                if owner:
                    add_class(owner)
                    relationships.append({
                        "source": owner,
                        "relationship": "HAS_METHOD",
                        "target": method_name,
                    })
        elif function_name and not inside_function:
            if current_class:
                qualified = f"{current_class}.{function_name}"
                entities["methods"].append(qualified)
                relationships.append({
                    "source": current_class,
                    "relationship": "HAS_METHOD",
                    "target": qualified,
                })
            else:
                entities["functions"].append(function_name)
                relationships.append({
                    "source": str(file_path),
                    "relationship": "DEFINES",
                    "target": function_name,
                })

        nested = inside_function or bool(function_name or method_name)
        for child in node.children:
            visit(child, current_class, nested)

    visit(tree.root_node)
    return {"entities": entities, "relationships": relationships}
