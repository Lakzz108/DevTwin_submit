"""Language identification shared by scanning and syntax parsing."""

from pathlib import Path


LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".go": "go",
}

DISPLAY_LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript JSX",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript JSX",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".h": "C/C++ header",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++ header",
    ".hxx": "C++ header",
    ".cs": "C#",
    ".go": "Go",
}


def detect_language(path):
    """Return the internal Tree-sitter language code, or ``None``."""

    return LANGUAGE_BY_EXTENSION.get(Path(path).suffix.lower())


def display_language(path):
    """Return a readable language label for a supported source path."""

    return DISPLAY_LANGUAGE_BY_EXTENSION.get(Path(path).suffix.lower())
