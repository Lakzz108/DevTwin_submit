from code_parser import parse_python_file, print_tree


file_path = "parser/repository_loader.py"

tree = parse_python_file(file_path)

with open(file_path, "rb") as file:
    source_code = file.read()

print("Tree-sitter syntax tree:\n")

print_tree(tree.root_node, source_code)