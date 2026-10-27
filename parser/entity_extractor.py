from multi_language_parser import parse_source_file


def extract_entities(file_path: str):
    """Extract normalized symbols and source relationships for one file."""

    result = parse_source_file(file_path)
    entities = result["entities"]
    relationships = []
    for name in entities["classes"] + entities["interfaces"] + entities["functions"]:
        relationships.append({"source": file_path, "relationship": "DEFINES", "target": name})
    for method in entities["methods"]:
        class_name = method.rsplit(".", 1)[0]
        relationships.append({"source": class_name, "relationship": "HAS_METHOD", "target": method})
    for record in entities["import_records"]:
        relationships.append({"source": file_path, "relationship": "IMPORTS", "target": record["module"]})
    return {"entities": entities, "relationships": relationships}
