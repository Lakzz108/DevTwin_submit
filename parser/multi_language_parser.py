"""Extract shared repository entities from Tree-sitter syntax trees."""

import re

from tree_sitter_language_pack import get_parser

from language_detector import detect_language


CLASS_NODES = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration"},
    "tsx": {"class_declaration"},
    "java": {"class_declaration"},
    "c": {"struct_specifier"},
    "cpp": {"class_specifier", "struct_specifier"},
    "csharp": {"class_declaration", "record_declaration"},
    "go": set(),
}
INTERFACE_NODES = {
    "python": set(), "javascript": set(),
    "typescript": {"interface_declaration"}, "tsx": {"interface_declaration"},
    "java": {"interface_declaration"}, "c": set(), "cpp": set(),
    "csharp": {"interface_declaration"}, "go": set(),
}
FUNCTION_NODES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "generator_function_declaration", "method_definition"},
    "typescript": {"function_declaration", "generator_function_declaration", "method_definition", "method_signature"},
    "tsx": {"function_declaration", "generator_function_declaration", "method_definition", "method_signature"},
    "java": {"method_declaration", "constructor_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
    "csharp": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
}
CALL_NODES = {
    "python": {"call"},
    "javascript": {"call_expression"}, "typescript": {"call_expression"}, "tsx": {"call_expression"},
    "java": {"method_invocation", "object_creation_expression"},
    "c": {"call_expression"}, "cpp": {"call_expression"},
    "csharp": {"invocation_expression", "object_creation_expression"},
    "go": {"call_expression"},
}
IMPORT_NODES = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"}, "typescript": {"import_statement"}, "tsx": {"import_statement"},
    "java": {"import_declaration"}, "c": {"preproc_include"}, "cpp": {"preproc_include"},
    "csharp": {"using_directive"}, "go": {"import_spec"},
}
API_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
_IDENTIFIER_TYPES = {
    "identifier", "type_identifier", "field_identifier", "property_identifier",
    "scoped_identifier", "scoped_type_identifier", "qualified_identifier",
    "nested_type_identifier",
}


def parse_source_file(file_path):
    """Parse one supported source file and return normalized structural facts."""

    detected = detect_language(file_path)
    if detected is None:
        raise ValueError(f"Unsupported source language: {file_path}")
    display_language, grammar_name = detected
    with open(file_path, "rb") as source_file:
        source = source_file.read()
    tree = get_parser(grammar_name).parse(source)
    relative_name = str(file_path)
    entities = {
        "file": relative_name,
        "language": display_language,
        "classes": [], "interfaces": [], "functions": [], "methods": [],
        "imports": [], "import_records": [], "exports": [], "calls": [],
        "inheritance": [], "api_endpoints": [], "symbols": [],
        "package": None, "entry_points": [],
        "parse_error": tree.root_node.has_error,
    }

    class_nodes = CLASS_NODES[grammar_name]
    interface_nodes = INTERFACE_NODES[grammar_name]
    function_nodes = FUNCTION_NODES[grammar_name]
    import_nodes = IMPORT_NODES[grammar_name]
    seen_symbols = set()
    seen_imports = set()
    seen_calls = set()
    seen_endpoints = set()

    def add_symbol(kind, name, node, qualified=None):
        qualified_name = qualified or name
        identity = (kind, qualified_name)
        if not name or identity in seen_symbols:
            return qualified_name
        seen_symbols.add(identity)
        entities[{
            "CLASS": "classes", "INTERFACE": "interfaces",
            "FUNCTION": "functions", "METHOD": "methods",
        }[kind]].append(qualified_name)
        entities["symbols"].append({
            "type": kind,
            "name": name,
            "qualified_name": qualified_name,
            "start_line": _line_at(source, node.start_byte),
            "end_line": _end_line_at(source, node.end_byte),
        })
        return qualified_name

    def add_import(node):
        for record in _import_records(grammar_name, node):
            add_import_record(record, node)

    def add_import_record(record, node):
        key = (record["module"], record.get("kind"), tuple(record.get("names", ())))
        if not record["module"] or key in seen_imports:
            return
        seen_imports.add(key)
        record["line"] = _line_at(source, node.start_byte)
        entities["import_records"].append(record)
        entities["imports"].append(record["module"])

    def add_endpoint(method, path, handler, node):
        key = (method, path, handler)
        if path and key not in seen_endpoints:
            seen_endpoints.add(key)
            entities["api_endpoints"].append({
                "method": method.upper(), "path": path, "handler": handler,
                "line": _line_at(source, node.start_byte),
            })

    def visit(node, current_class=None, current_symbol=None):
        node_text = _text(node)

        if grammar_name == "go" and node.type == "package_clause":
            package_name = next((child for child in node.named_children if child.type == "package_identifier"), None)
            entities["package"] = _text(package_name) if package_name else None
        elif grammar_name == "java" and node.type == "package_declaration":
            entities["package"] = next((_text(child) for child in node.named_children if child.type in _IDENTIFIER_TYPES), None)
        elif grammar_name == "csharp" and node.type == "namespace_declaration":
            entities["package"] = _text(node.child_by_field_name("name")) or None

        if node.type == "type_spec" and grammar_name == "go":
            name_node = node.child_by_field_name("name")
            type_node = node.child_by_field_name("type")
            if name_node and type_node and type_node.type in {"struct_type", "interface_type"}:
                name = _text(name_node)
                kind = "INTERFACE" if type_node.type == "interface_type" else "CLASS"
                add_symbol(kind, name, node)
                if kind == "CLASS":
                    current_class = name

        elif node.type in class_nodes | interface_nodes:
            name_node = node.child_by_field_name("name")
            if name_node is None and grammar_name in {"c", "cpp"}:
                name_node = node.child_by_field_name("name")
            name = _text(name_node) if name_node else ""
            kind = "INTERFACE" if node.type in interface_nodes else "CLASS"
            qualified_name = add_symbol(kind, name, node)
            current_class = qualified_name
            for parent_name, relationship in _base_types(grammar_name, node):
                entities["inheritance"].append({
                    "child": qualified_name, "parent": parent_name,
                    "relationship": relationship,
                })

        is_function = node.type in function_nodes
        assigned_function = _assigned_function(grammar_name, node)
        if (is_function or assigned_function) and current_symbol is None:
            name_node = node.child_by_field_name("name") if is_function else assigned_function
            name = _text(name_node) if name_node else _declarator_name(node)
            class_name = current_class
            if grammar_name == "go" and node.type == "method_declaration":
                class_name = _go_receiver_type(node) or current_class
            qualified_name = f"{class_name}.{name}" if class_name else name
            kind = "METHOD" if class_name else "FUNCTION"
            current_symbol = add_symbol(kind, name, node, qualified_name)
            if _is_entry_point(grammar_name, name, node, entities):
                entities["entry_points"].append({
                    "name": qualified_name,
                    "evidence": f"{display_language} entry function/method declared in source",
                    "line": _line_at(source, node.start_byte),
                })

        if node.type in import_nodes:
            add_import(node)

        if node.type in CALL_NODES[grammar_name]:
            if grammar_name in {"javascript", "typescript", "tsx"}:
                import_record = _javascript_require_record(node)
                if import_record:
                    add_import_record(import_record, node)
            if current_symbol:
                callee, receiver = _call_name(grammar_name, node)
            else:
                callee, receiver = "", None
            if current_symbol and callee and callee not in {"if", "for", "while", "switch", "catch"}:
                call_key = (current_symbol, callee, receiver, node.start_byte)
                if call_key not in seen_calls:
                    seen_calls.add(call_key)
                    entities["calls"].append({
                        "caller": current_symbol, "callee": callee,
                        "receiver": receiver,
                        "line": _line_at(source, node.start_byte),
                    })
            if grammar_name in {"javascript", "typescript", "tsx"}:
                endpoint = _express_route(node)
                if endpoint:
                    method, path, handler = endpoint
                    add_endpoint(method, path, handler, node)

        if node.type == "decorated_definition" and grammar_name == "python":
            for method, path in _python_route_decorators(node):
                handler = _decorated_function_name(node)
                add_endpoint(method, path, handler, node)

        if node.type == "export_statement" and grammar_name in {"javascript", "typescript", "tsx"}:
            entities["exports"].extend(_exported_names(node))

        for child in node.named_children:
            # Don't descend into a function a second time via its assigned
            # arrow-function value; the outer variable declarator owns its name.
            if assigned_function and child.type in {"arrow_function", "function_expression"}:
                for nested in child.named_children:
                    visit(nested, current_class, current_symbol)
            else:
                visit(child, current_class, current_symbol)

    visit(tree.root_node)
    entities["imports"] = list(dict.fromkeys(entities["imports"]))
    entities["exports"] = list(dict.fromkeys(entities["exports"]))
    return {"entities": entities, "relationships": []}


def _text(node):
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def _line_at(source, byte_offset):
    return source.count(b"\n", 0, byte_offset) + 1


def _end_line_at(source, byte_offset):
    line = source.count(b"\n", 0, byte_offset)
    if byte_offset == 0 or source[byte_offset - 1] != 0x0A:
        line += 1
    return max(1, line)


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _import_records(language, node):
    text = _text(node).strip()
    if language == "python":
        if node.type == "import_statement":
            body = re.sub(r"^import\s+", "", text).strip()
            for item in body.split(","):
                module = item.strip().split(" as ", 1)[0].strip()
                if module:
                    yield {"module": module, "kind": "python_import", "names": []}
            return
        match = re.match(r"from\s+([.]*[\w.]*)\s+import\s+(.+)$", text, re.S)
        if match:
            raw_module, raw_names = match.groups()
            level = len(raw_module) - len(raw_module.lstrip("."))
            module = raw_module[level:]
            names = [part.strip().split(" as ", 1)[0] for part in raw_names.strip("() ").split(",") if part.strip()]
            yield {"module": module, "level": level, "kind": "python_from", "names": names}
        return
    if language in {"javascript", "typescript", "tsx"}:
        if node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            module = _unquote(_text(source_node))
            names = [_text(item.child_by_field_name("name")) for item in _walk(node) if item.type == "import_specifier"]
        if module:
            yield {"module": module, "kind": "js_import", "names": [n for n in names if n]}
        return
    if language == "java":
        module = re.sub(r"^import\s+(?:static\s+)?|;\s*$", "", text).strip()
        if module:
            yield {"module": module, "kind": "java_import", "names": []}
        return
    if language in {"c", "cpp"}:
        path_node = node.child_by_field_name("path")
        raw_path = _text(path_node)
        module = _unquote(raw_path)
        if module:
            yield {"module": module, "kind": "include", "system": raw_path.startswith("<"), "names": []}
        return
    if language == "csharp":
        module = re.sub(r"^using\s+(?:static\s+)?|;\s*$", "", text).strip()
        if "=" in module:
            module = module.split("=", 1)[-1].strip()
        if module:
            yield {"module": module, "kind": "csharp_using", "names": []}
        return
    if language == "go":
        path_node = next((item for item in _walk(node) if item.type in {"interpreted_string_literal", "raw_string_literal"}), None)
        module = _unquote(_text(path_node))
        if module:
            yield {"module": module, "kind": "go_import", "names": []}


def _javascript_require_record(node):
    function = node.child_by_field_name("function")
    if _text(function).strip() not in {"require", "import"}:
        return None
    arguments = node.child_by_field_name("arguments")
    values = arguments.named_children if arguments else []
    if not values or values[0].type != "string":
        return None
    module = _unquote(_text(values[0]))
    return {"module": module, "kind": "js_import", "names": [], "syntax": "require"}


def _is_entry_point(language, name, node, entities):
    source = _text(node)
    if language in {"c", "cpp"}:
        return name == "main"
    if language == "go":
        return name == "main" and entities.get("package") == "main"
    if language == "java":
        return name == "main" and bool(re.search(r"\bstatic\b", source))
    if language == "csharp":
        return name == "Main" and bool(re.search(r"\bstatic\b", source))
    return False


def _unquote(value):
    value = value.strip()
    return value[1:-1] if len(value) >= 2 and value[0] in {'"', "'", "<", "`"} else value


def _name_nodes(node):
    return [_text(item) for item in _walk(node) if item.type in _IDENTIFIER_TYPES]


def _base_types(language, node):
    candidates = []
    mapping = {
        "python": ("superclasses", "EXTENDS"),
        "javascript": ("class_heritage", "EXTENDS"),
        "typescript": ("class_heritage", "EXTENDS"),
        "tsx": ("class_heritage", "EXTENDS"),
        "java": ("superclass", "EXTENDS"),
        "cpp": ("base_class_clause", "EXTENDS"),
        "csharp": ("base_list", "EXTENDS"),
    }
    field_and_type = mapping.get(language)
    if field_and_type:
        field, default_relationship = field_and_type
        parent_node = node.child_by_field_name(field)
        if parent_node is None and language == "cpp":
            parent_node = next((item for item in _walk(node) if item.type == "base_class_clause"), None)
        if parent_node is None and language == "csharp":
            parent_node = next((item for item in _walk(node) if item.type == "base_list"), None)
        if parent_node:
            for candidate in _walk(parent_node):
                if candidate.type not in _IDENTIFIER_TYPES:
                    continue
                relationship = default_relationship
                if candidate.parent and candidate.parent.type in {"implements_clause", "super_interfaces"}:
                    relationship = "IMPLEMENTS"
                if language == "python" and candidate.parent and candidate.parent.type == "argument_list":
                    relationship = "EXTENDS"
                candidates.append((_text(candidate), relationship))
    if language == "java":
        interfaces = node.child_by_field_name("interfaces") or node.child_by_field_name("super_interfaces")
        if interfaces:
            candidates.extend((_text(item), "IMPLEMENTS") for item in _walk(interfaces) if item.type in _IDENTIFIER_TYPES)
    if language == "csharp":
        base = node.child_by_field_name("bases") or node.child_by_field_name("base_list")
        # C# syntax does not distinguish a base class and interfaces in the AST.
        if base:
            candidates = [(_text(item), "EXTENDS") for item in _walk(base) if item.type in _IDENTIFIER_TYPES]
    return list(dict.fromkeys(candidates))


def _declarator_name(node):
    declarator = next((item for item in _walk(node) if item.type in {"function_declarator", "method_declaration"}), None)
    if declarator is not None:
        named = declarator.child_by_field_name("declarator") or declarator.child_by_field_name("name")
        if named:
            names = [item for item in _walk(named) if item.type in _IDENTIFIER_TYPES]
            if names:
                return _text(names[-1])
    names = [item for item in _walk(node) if item.type in _IDENTIFIER_TYPES]
    return _text(names[0]) if names else ""


def _assigned_function(language, node):
    if language not in {"javascript", "typescript", "tsx"} or node.type != "variable_declarator":
        return None
    value = node.child_by_field_name("value")
    if value and value.type in {"arrow_function", "function_expression"}:
        return node.child_by_field_name("name")
    return None


def _go_receiver_type(node):
    receiver = node.child_by_field_name("receiver")
    identifiers = [item for item in _walk(receiver) if item.type in _IDENTIFIER_TYPES] if receiver else []
    if len(identifiers) >= 2:
        return _text(identifiers[-1]).lstrip("*")
    if identifiers:
        return _text(identifiers[-1]).lstrip("*")
    return None


def _call_name(language, node):
    field = node.child_by_field_name("function") or node.child_by_field_name("name")
    if field is None:
        field = next((child for child in node.named_children if child.type not in {"argument_list", "arguments"}), None)
    text = _text(field).strip()
    receiver = None
    callee = text
    if field and field.type in {"member_expression", "selector_expression", "scoped_identifier", "field_expression"}:
        prop = field.child_by_field_name("property") or field.child_by_field_name("field") or field.child_by_field_name("name")
        obj = field.child_by_field_name("object") or field.child_by_field_name("operand") or field.child_by_field_name("scope")
        if prop:
            callee = _text(prop)
        if obj:
            receiver = _text(obj)
    if language == "java" and field and field.type == "identifier":
        callee = text
    return callee, receiver


def _express_route(node):
    function = node.child_by_field_name("function")
    function_text = _text(function)
    method = function_text.rsplit(".", 1)[-1].lower()
    if method not in API_METHODS and method != "use":
        return None
    args = node.child_by_field_name("arguments")
    values = args.named_children if args else []
    if not values:
        return None
    path = _unquote(_text(values[0]))
    if not path.startswith(("/", "*", ":")):
        return None
    handler = _text(values[1]) if len(values) > 1 else ""
    return method.upper(), path, handler


def _python_route_decorators(node):
    text = _text(node)
    for match in re.finditer(r"@(?:[\w.]+\.)?(get|post|put|patch|delete|options|head)\s*\(\s*(['\"])(.*?)\2", text, re.I):
        yield match.group(1).upper(), match.group(3)
    route = re.search(r"@(?:[\w.]+\.)?route\s*\(\s*(['\"])(.*?)\1(.*?)\)", text, re.S)
    if route:
        methods = re.search(r"methods\s*=\s*\[([^]]+)\]", route.group(3), re.I)
        found = re.findall(r"['\"]([A-Za-z]+)['\"]", methods.group(1)) if methods else ["GET"]
        for method in found:
            yield method.upper(), route.group(2)


def _decorated_function_name(node):
    function = next((item for item in _walk(node) if item.type in {"function_definition", "function_declaration", "method_declaration"}), None)
    name = function.child_by_field_name("name") if function else None
    return _text(name) if name else ""


def _exported_names(node):
    declaration = node.child_by_field_name("declaration")
    if declaration:
        name = declaration.child_by_field_name("name")
        if name:
            return [_text(name)]
        # Variable declarations can export one or more named bindings.
        names = []
        for child in _walk(declaration):
            if child.type == "variable_declarator":
                variable = child.child_by_field_name("name")
                if variable:
                    names.append(_text(variable))
        return names
    names = []
    for child in _walk(node):
        if child.type == "export_specifier":
            name = child.child_by_field_name("name") or child.child_by_field_name("alias")
            if name:
                names.append(_text(name))
    return names
