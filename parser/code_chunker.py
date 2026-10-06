"""Create line-aware retrieval chunks for Python source files."""

from pathlib import Path

from code_parser import parse_python_file


DEFAULT_MAX_CHARS = 12000
OVERLAP_LINES = 2


def build_code_chunks(
    file_path,
    repository_id=None,
    max_characters=DEFAULT_MAX_CHARS,
    relative_path=None,
):
    """Extract class/function chunks and module-level context from a Python file.

    Large symbols are split on line boundaries with a small overlap, while
    every chunk retains its symbol and source line range.
    """

    if max_characters < 1:
        raise ValueError("max_characters must be greater than zero")

    source_path = Path(file_path)
    chunk_file_path = (
        Path(relative_path).as_posix()
        if relative_path is not None
        else source_path.as_posix()
    )
    source_bytes = source_path.read_bytes()
    source_lines = source_bytes.decode("utf-8").splitlines()
    tree = parse_python_file(str(source_path))
    chunks = []
    symbol_nodes = []

    def add_chunks(node, kind, symbol, class_name=None):
        # Compute lines from byte offsets. Avoid Point.column: the installed
        # Tree-sitter binding has an Apple Silicon crash report involving that
        # property, and byte offsets are already available on every node.
        start_byte = node.start_byte
        end_byte = node.end_byte
        start_line = source_bytes.count(b"\n", 0, start_byte) + 1
        end_line = source_bytes.count(b"\n", 0, end_byte)
        if end_byte == 0 or source_bytes[end_byte - 1] != 0x0A:
            end_line += 1
        end_line = max(start_line, end_line)
        content = node.text.decode("utf-8", errors="replace")
        symbol_nodes.append((start_line, end_line))

        parts = _split_content(content, max_characters)
        for part_index, (part_content, relative_start, relative_end) in enumerate(parts, 1):
            chunk = {
                "id": (
                    f"chunk:{chunk_file_path}:{kind}:"
                    f"{symbol}:{start_line + relative_start}:part-{part_index}"
                ),
                "file": chunk_file_path,
                "kind": kind,
                "symbol": symbol,
                "class_name": class_name,
                "start_line": start_line + relative_start,
                "end_line": min(end_line, start_line + relative_end),
                "content": part_content,
            }
            if repository_id is not None:
                chunk["repository_id"] = repository_id
            chunks.append(chunk)

    def visit(node, class_stack=(), inside_function=False):
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
            nested_stack = (*class_stack, class_name)
            qualified_name = ".".join(nested_stack)
            add_chunks(node, "CLASS", qualified_name, class_name=qualified_name)
            for child in node.named_children:
                visit(child, nested_stack, inside_function=False)
            return

        if node.type == "function_definition":
            if inside_function:
                return
            name_node = node.child_by_field_name("name")
            function_name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
            if class_stack:
                kind = "METHOD"
                qualified_name = f"{'.'.join(class_stack)}.{function_name}"
                class_name = ".".join(class_stack)
            else:
                kind = "FUNCTION"
                qualified_name = function_name
                class_name = None
            add_chunks(node, kind, qualified_name, class_name=class_name)
            return

        for child in node.named_children:
            visit(child, class_stack, inside_function)

    visit(tree.root_node)

    if symbol_nodes:
        first_symbol_line = min(start for start, _ in symbol_nodes)
        module_context = "\n".join(source_lines[:first_symbol_line - 1]).strip()
        if module_context:
            context_chunk = {
                "id": f"chunk:{chunk_file_path}:MODULE_CONTEXT:1:part-1",
                "file": chunk_file_path,
                "kind": "MODULE_CONTEXT",
                "symbol": None,
                "class_name": None,
                "start_line": 1,
                "end_line": first_symbol_line - 1,
                "content": module_context,
            }
            if repository_id is not None:
                context_chunk["repository_id"] = repository_id
            chunks.insert(0, context_chunk)
    elif source_bytes.strip():
        content = source_bytes.decode("utf-8", errors="replace")
        for part_index, (part_content, start_offset, end_offset) in enumerate(
            _split_content(content, max_characters),
            1,
        ):
            chunk = {
                "id": f"chunk:{chunk_file_path}:MODULE:1:part-{part_index}",
                "file": chunk_file_path,
                "kind": "MODULE",
                "symbol": None,
                "class_name": None,
                "start_line": start_offset + 1,
                "end_line": end_offset + 1,
                "content": part_content,
            }
            if repository_id is not None:
                chunk["repository_id"] = repository_id
            chunks.append(chunk)

    return chunks


def _split_content(content, max_characters):
    """Split content on line boundaries and overlap consecutive chunks."""

    lines = content.splitlines()
    if not lines:
        return [(content, 0, 0)]
    if len(content) <= max_characters:
        return [(content, 0, len(lines) - 1)]

    parts = []
    start = 0
    while start < len(lines):
        end = start
        length = 0
        while end < len(lines):
            next_length = len(lines[end]) + (1 if end > start else 0)
            if end > start and length + next_length > max_characters:
                break
            length += next_length
            end += 1

        parts.append(("\n".join(lines[start:end]), start, end - 1))
        if end >= len(lines):
            break
        start = max(start + 1, end - OVERLAP_LINES)

    return parts
