from repository_analyzer import analyze_repository


result = analyze_repository(".")


print("REPOSITORY ANALYSIS")
print("===================")

print("\nFiles analyzed:")

for file_info in result["files"]:
    print("\nFile:", file_info["file"])

    print("Classes:", file_info["classes"])
    print("Functions:", file_info["functions"])
    print("Methods:", file_info["methods"])
    print("Imports:", file_info["imports"])


print("\n\nRELATIONSHIPS")
print("=============")

for relationship in result["relationships"]:
    print(
        f"{relationship['source']} "
        f"--[{relationship['relationship']}]--> "
        f"{relationship['target']}"
    )