from entity_extractor import extract_entities


file_path = "parser/repository_loader.py"

result = extract_entities(file_path)

entities = result["entities"]
relationships = result["relationships"]


print("EXTRACTED ENTITIES")
print("==================")

print("\nFile:")
print(entities["file"])

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


print("\n\nRELATIONSHIPS")
print("=============")

for relationship in relationships:
    print(
        f"{relationship['source']} "
        f"--[{relationship['relationship']}]--> "
        f"{relationship['target']}"
    )