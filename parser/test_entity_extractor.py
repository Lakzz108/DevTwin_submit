from entity_extractor import extract_entities


file_path = "parser/repository_loader.py"

entities = extract_entities(file_path)

print("Extracted Repository Information")
print("--------------------------------")

print("File:", entities["file"])

print("\nClasses:")
for item in entities["classes"]:
    print(" -", item)

print("\nFunctions:")
for item in entities["functions"]:
    print(" -", item)

print("\nMethods:")
for item in entities["methods"]:
    print(" -", item)

print("\nImports:")
for item in entities["imports"]:
    print(" -", item)