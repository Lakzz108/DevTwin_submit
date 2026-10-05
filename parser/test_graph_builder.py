from repository_analyzer import analyze_repository
from graph_builder import build_graph_data


# Analyze the repository
analysis_result = analyze_repository(".")


# Convert repository analysis into graph-ready data
graph_data = build_graph_data(analysis_result)


print("GRAPH NODES")
print("===========")

for node in graph_data["nodes"]:

    print(
        f"{node['id']} "
        f"[{node['type']}] "
        f"{node['name']}"
    )


print("\n\nGRAPH RELATIONSHIPS")
print("===================")

for relationship in graph_data["relationships"]:

    print(
        f"{relationship['source']} "
        f"--[{relationship['relationship']}]--> "
        f"{relationship['target']}"
    )