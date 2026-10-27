"""Detect source languages supported by DevTwin's Tree-sitter parsers."""

from pathlib import Path


EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".go": "go",
}


def detect_language(file_path):
    """Return the normalized language name for a supported source file."""

    return EXTENSION_LANGUAGES.get(Path(file_path).suffix.lower())
