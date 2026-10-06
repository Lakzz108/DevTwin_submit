"""Build retrieval chunks for supported Python files in a repository."""

from pathlib import Path

from code_chunker import build_code_chunks
from repository_analyzer import analyze_repository


def build_repository_chunks(repo_path, repository_id=None, analysis_result=None):
    """Chunk Python files while keeping paths relative to the repository."""

    repository_root = Path(repo_path).resolve()
    if analysis_result is None:
        analysis_result = analyze_repository(repo_path)

    chunks = []
    for file_info in analysis_result["files"]:
        relative_path = Path(file_info["file"])
        if relative_path.suffix.lower() != ".py":
            continue

        source_path = repository_root / relative_path
        chunks.extend(build_code_chunks(
            source_path,
            repository_id=repository_id,
            relative_path=relative_path.as_posix(),
        ))

    return chunks
