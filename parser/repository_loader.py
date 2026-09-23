from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
}


def scan_repository(repo_path: str):
    """
    Scan a repository and return all supported source-code files.
    """

    repo = Path(repo_path)

    if not repo.exists():
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    if not repo.is_dir():
        raise NotADirectoryError(f"Not a directory: {repo_path}")

    source_files = []

    for file in repo.rglob("*"):
        if not file.is_file():
            continue

        # Ignore common unnecessary directories
        if any(
            part in {
                ".git",
                ".venv",
                "node_modules",
                "__pycache__",
                "dist",
                "build",
            }
            for part in file.parts
        ):
            continue

        if file.suffix.lower() in SUPPORTED_EXTENSIONS:
            source_files.append(file)

    return source_files