from repository_loader import scan_repository
from entity_extractor import extract_entities


def analyze_repository(repo_path: str):
    """
    Analyze all supported source files in a repository.

    Returns combined entities and relationships
    from the entire repository.
    """

    source_files = scan_repository(repo_path)

    all_entities = []
    all_relationships = []

    for file_path in source_files:
        result = extract_entities(file_path)

        all_entities.append(result["entities"])
        all_relationships.extend(result["relationships"])

    return {
        "files": all_entities,
        "relationships": all_relationships,
    }