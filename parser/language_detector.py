"""Language identification shared by scanning and syntax parsing."""

from pathlib import Path


LANGUAGE_BY_EXTENSION = {
    ".py": ("Python", "python"),
    ".js": ("JavaScript", "javascript"),
    ".jsx": ("JavaScript JSX", "javascript"),
    ".mjs": ("JavaScript", "javascript"),
    ".cjs": ("JavaScript", "javascript"),
    ".ts": ("TypeScript", "typescript"),
    ".tsx": ("TypeScript JSX", "tsx"),
    ".mts": ("TypeScript", "typescript"),
    ".cts": ("TypeScript", "typescript"),
    ".java": ("Java", "java"),
    ".c": ("C", "c"),
    # Headers commonly contain either dialect; the C++ grammar accepts the
    # shared C declarations while also handling class declarations.
    ".h": ("C/C++ header", "cpp"),
    ".cpp": ("C++", "cpp"),
    ".cc": ("C++", "cpp"),
    ".cxx": ("C++", "cpp"),
    ".hpp": ("C++ header", "cpp"),
    ".hxx": ("C++ header", "cpp"),
    ".cs": ("C#", "csharp"),
    ".go": ("Go", "go"),
}


def detect_language(path):
    """Return display and Tree-sitter language names for a source path."""

    return LANGUAGE_BY_EXTENSION.get(Path(path).suffix.lower())
