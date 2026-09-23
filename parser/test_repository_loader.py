from repository_loader import scan_repository


files = scan_repository(".")


print("Source files found:")

for file in files:
    print(file)
