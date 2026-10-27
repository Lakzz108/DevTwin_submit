from pathlib import Path

from entity_extractor import extract_entities
from import_resolver import resolve_imports
from repository_loader import scan_repository


def analyze_repository(repo_path: str):
    """
    Analyze all supported source files in a repository.

    Returns combined entities and relationships
    from the entire repository.
    """

    repository_root = Path(repo_path).resolve()
    source_files = scan_repository(repo_path)

    all_entities = []
    all_relationships = []

    for file_path in source_files:
        result = extract_entities(str(file_path))

        # Store paths relative to the repository so graph IDs do not depend on
        # where the repository was checked out or how it was passed in.
        relative_file_path = Path(file_path).resolve().relative_to(
            repository_root
        ).as_posix()
        result["entities"]["file"] = relative_file_path

        all_entities.append(result["entities"])

        for relationship in result["relationships"]:
            if relationship["source"] == str(file_path):
                relationship["source"] = relative_file_path
            all_relationships.append(relationship)

    import_summary = resolve_imports(repository_root, all_entities)

    return {
        "files": all_entities,
        "relationships": all_relationships,
        "repository_name": repository_root.name,
        "import_summary": import_summary,
    }
