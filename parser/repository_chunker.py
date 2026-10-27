"""Build line-aware retrieval chunks for parsed repository source files."""

from pathlib import Path

from code_chunker import build_code_chunks
from language_detector import detect_language
from repository_analyzer import analyze_repository


MAX_CHUNK_CHARACTERS = 12000
OVERLAP_LINES = 2


def build_repository_chunks(repo_path, repository_id=None, analysis_result=None):
    """Chunk all parsed languages and attach file, symbol and source metadata."""

    repository_root = Path(repo_path).resolve()
    if analysis_result is None:
        analysis_result = analyze_repository(repo_path)

    chunks = []
    for file_info in analysis_result["files"]:
        relative_path = Path(file_info["file"])
        detected = detect_language(relative_path)
        if detected is None:
            continue

        source_path = repository_root / relative_path
        if relative_path.suffix.lower() == ".py":
            file_chunks = build_code_chunks(
                source_path,
                repository_id=repository_id,
                relative_path=relative_path.as_posix(),
            )
        else:
            file_chunks = _build_syntax_chunks(source_path, file_info, repository_id)
        for chunk in file_chunks:
            chunk["language"] = file_info.get("language", detected[0])
            chunk["repository"] = analysis_result.get("repository_name", repository_root.name)
        chunks.extend(file_chunks)

    return chunks


def _build_syntax_chunks(source_path, file_info, repository_id):
    relative_path = file_info["file"]
    content = source_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    chunks = []
    symbols = file_info.get("symbols", [])

    for symbol in symbols:
        start = max(1, symbol["start_line"])
        end = max(start, symbol["end_line"])
        symbol_lines = lines[start - 1:end]
        text = "\n".join(symbol_lines).strip()
        if not text:
            continue
        for part_index, (part_text, part_start, part_end) in enumerate(_split_lines(text), 1):
            chunk = {
                "id": f"chunk:{relative_path}:{symbol['type']}:{symbol['qualified_name']}:{start + part_start}:part-{part_index}",
                "file": relative_path,
                "kind": symbol["type"],
                "symbol_kind": symbol["type"],
                "entity_type": symbol["type"],
                "symbol": symbol["qualified_name"],
                "class_name": symbol["qualified_name"].rsplit(".", 1)[0] if symbol["type"] == "METHOD" else None,
                "start_line": start + part_start,
                "end_line": min(end, start + part_end),
                "content": part_text,
            }
            if repository_id is not None:
                chunk["repository_id"] = repository_id
            chunks.append(chunk)

    if symbols:
        first_line = min(symbol["start_line"] for symbol in symbols)
        context = "\n".join(lines[:max(0, first_line - 1)]).strip()
        if context:
            chunks.append(_module_chunk(relative_path, context, 1, first_line - 1, repository_id))
    elif content.strip():
        for part_index, (part_text, start, end) in enumerate(_split_lines(content), 1):
            chunks.append(_module_chunk(relative_path, part_text, start + 1, end + 1, repository_id, part_index))
    return chunks


def _module_chunk(file_path, content, start_line, end_line, repository_id, part_index=1):
    chunk = {
        "id": f"chunk:{file_path}:MODULE_CONTEXT:{start_line}:part-{part_index}",
        "file": file_path,
        "kind": "MODULE_CONTEXT",
        "symbol_kind": "MODULE_CONTEXT",
        "entity_type": "FILE",
        "symbol": None,
        "class_name": None,
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
    }
    if repository_id is not None:
        chunk["repository_id"] = repository_id
    return chunk


def _split_lines(content):
    lines = content.splitlines()
    if not lines:
        return [(content, 0, 0)]
    if len(content) <= MAX_CHUNK_CHARACTERS:
        return [(content, 0, len(lines) - 1)]
    parts = []
    start = 0
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines):
            next_size = len(lines[end]) + (1 if end > start else 0)
            if end > start and size + next_size > MAX_CHUNK_CHARACTERS:
                break
            size += next_size
            end += 1
        parts.append(("\n".join(lines[start:end]), start, end - 1))
        if end >= len(lines):
            break
        start = max(start + 1, end - OVERLAP_LINES)
    return parts
