"""Resolve source imports to repository files or explain why they remain external."""

import importlib.util
import json
import os
import re
import sys
import tomllib
from collections import defaultdict
from pathlib import Path


SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".java", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".cs", ".go"}
JS_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")
BUILTIN_JS = {"assert", "buffer", "child_process", "crypto", "events", "fs", "http", "https", "module", "os", "path", "process", "stream", "url", "util", "zlib"}


def resolve_imports(repository_root, files):
    """Annotate every extracted import with an internal/external/unresolved target."""

    root = Path(repository_root).resolve()
    indexes = _build_file_indexes(files)
    dependencies = _declared_dependencies(root)
    go_module = _go_module(root)
    summary = {"total": 0, "internal": 0, "external": 0, "unresolved": 0}

    package_names = defaultdict(set)
    for file_info in files:
        if file_info.get("language") == "Go" and file_info.get("package"):
            package_names[Path(file_info["file"]).parent.as_posix()].add(file_info["package"])
    for file_info in files:
        for record in file_info.get("import_records", []):
            summary["total"] += 1
            if record.get("kind") == "go_import":
                package_path = _go_package_path(record["module"], go_module, indexes["directories"])
                if package_path is not None:
                    names = package_names.get(package_path, set())
                    record.update({
                        "resolution": "internal",
                        "target_package": package_path,
                        "target_package_name": next(iter(names)) if len(names) == 1 else Path(package_path).name,
                    })
                    summary["internal"] += 1
                    continue
            resolved_file = _resolve_record(record, file_info["file"], indexes, go_module)
            if resolved_file:
                record.update({"resolution": "internal", "target_file": resolved_file})
                summary["internal"] += 1
                continue

            if _is_external(record, dependencies):
                record["resolution"] = "external"
                summary["external"] += 1
            else:
                record["resolution"] = "unresolved"
                summary["unresolved"] += 1
            record["target_module"] = record["module"]

    return summary


def _build_file_indexes(files):
    modules = defaultdict(set)
    directories = defaultdict(set)
    paths = set()
    for info in files:
        path = Path(info["file"])
        relative = path.as_posix()
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        paths.add(relative)
        directories[path.parent.as_posix()].add(relative)
        no_suffix = path.with_suffix("")
        dotted = ".".join(no_suffix.parts)
        _add_module(modules, dotted, relative)
        _add_module(modules, no_suffix.name, relative)
        # Python package files name the directory package, and common src roots
        # are not part of import statements (src/app/auth.py -> app.auth).
        if path.name == "__init__.py":
            _add_module(modules, ".".join(path.parent.parts), relative)
        if no_suffix.parts and no_suffix.parts[0].lower() in {"src", "lib", "source"}:
            _add_module(modules, ".".join(no_suffix.parts[1:]), relative)
        if path.suffix.lower() in JS_SUFFIXES and path.stem == "index":
            _add_module(modules, ".".join(path.parent.parts), relative)
    return {"modules": modules, "directories": directories, "paths": paths}


def _add_module(modules, name, file_path):
    if name:
        modules[name.replace("/", ".")] .add(file_path)


def _resolve_record(record, importer, indexes, go_module):
    module = record["module"].strip()
    language_kind = record.get("kind", "")
    if language_kind == "js_import":
        return _resolve_javascript(module, importer, indexes)
    if language_kind == "include":
        path = Path(importer).parent / module
        return _match_path(path.as_posix(), indexes)
    if language_kind == "go_import":
        return None
    if language_kind == "python_import":
        return _match_module(module, indexes["modules"])
    if language_kind == "python_from":
        base = _relative_python_module(importer, module, record.get("level", 0))
        for name in record.get("names", []):
            if name == "*":
                continue
            match = _match_module(f"{base}.{name}".strip("."), indexes["modules"])
            if match:
                return match
        match = _match_module(base, indexes["modules"])
        if match:
            return match
        return None
    if language_kind in {"java_import", "csharp_using"}:
        return _match_module(module, indexes["modules"])
    return _match_module(module, indexes["modules"])


def _relative_python_module(importer, module, level):
    if not level:
        return module
    path = Path(importer)
    package_parts = list(path.parent.parts)
    if path.name == "__init__.py":
        package_parts = list(path.parent.parts)
    ascend = max(0, level - 1)
    if ascend:
        package_parts = package_parts[:-ascend]
    return ".".join([*package_parts, module] if module else package_parts)


def _resolve_javascript(module, importer, indexes):
    if not module.startswith((".", "/")):
        return None
    base = Path(importer).parent / module
    normalized = base.as_posix()
    for candidate in (normalized, *(normalized + suffix for suffix in JS_SUFFIXES), *(normalized + "/index" + suffix for suffix in JS_SUFFIXES)):
        match = _match_path(candidate, indexes)
        if match:
            return match
    return None


def _match_path(candidate, indexes):
    normalized = Path(candidate).as_posix()
    paths = indexes.get("paths", set()) if isinstance(indexes, dict) else set()
    if normalized in paths:
        return normalized
    for suffix in SOURCE_SUFFIXES:
        normalized = normalized.removesuffix(suffix)
    normalized = normalized.removesuffix("/index")
    modules = indexes.get("modules", {}) if isinstance(indexes, dict) else indexes
    candidates = modules.get(normalized.replace("/", "."), set())
    return next(iter(candidates)) if len(candidates) == 1 else None


def _match_module(module, modules):
    module = module.replace("/", ".").strip(".")
    candidates = modules.get(module, set())
    if len(candidates) == 1:
        return next(iter(candidates))
    # Java imports often name a type inside a file, and package roots may be
    # checked out under src/main/java. Resolve an unambiguous module suffix.
    suffix_matches = set()
    for known, paths in modules.items():
        if known.endswith("." + module):
            suffix_matches.update(paths)
    return next(iter(suffix_matches)) if len(suffix_matches) == 1 else None


def _declared_dependencies(root):
    dependencies = set()
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "data", "repos"}
    manifests = []
    for current, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if name not in ignored]
        current_path = Path(current)
        manifests.extend(current_path / name for name in filenames if name == "package.json")
        manifests.extend(current_path / name for name in filenames if name.startswith("requirements") and name.endswith(".txt"))
        if "pyproject.toml" in filenames:
            manifests.append(current_path / "pyproject.toml")

    for package_json in (path for path in manifests if path.name == "package.json"):
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                dependencies.update(_package_root(name) for name in data.get(key, {}))
        except (OSError, ValueError, TypeError):
            pass
    for requirements in (path for path in manifests if path.name.startswith("requirements")):
        try:
            for line in requirements.read_text(encoding="utf-8").splitlines():
                match = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
                if match and not line.lstrip().startswith("#"):
                    dependencies.add(match.group(1).lower().replace("-", "_"))
        except OSError:
            pass
    for pyproject in (path for path in manifests if path.name == "pyproject.toml"):
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            declarations = data.get("project", {}).get("dependencies", [])
            for item in declarations:
                match = re.match(r"\s*([A-Za-z0-9_.-]+)", item)
                if match:
                    dependencies.add(match.group(1).lower().replace("-", "_"))
        except (OSError, ValueError, TypeError):
            pass
    return dependencies


def _package_root(name):
    return name.split("/", 1)[0].lstrip("@").lower().replace("-", "_")


def _is_external(record, dependencies):
    module = record["module"].strip()
    kind = record.get("kind", "")
    root_name = module.split(".", 1)[0].split("/", 1)[0].lower().replace("-", "_")
    if kind == "include":
        return bool(record.get("system"))
    if kind == "go_import":
        return "." not in module.split("/", 1)[0]
    if kind == "java_import":
        return module.startswith(("java.", "javax.", "jakarta.")) or root_name in dependencies
    if kind == "csharp_using":
        return module.startswith(("System", "Microsoft")) or root_name.lower() in dependencies
    if kind in {"js_import"}:
        return module.startswith("node:") or root_name in BUILTIN_JS or root_name in dependencies
    if kind.startswith("python"):
        return root_name in sys.stdlib_module_names or root_name in dependencies or _installed_python_module(root_name)
    return root_name in dependencies


def _installed_python_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _go_module(root):
    path = root / "go.mod"
    if not path.is_file():
        return None
    try:
        match = re.search(r"^module\s+(\S+)", path.read_text(encoding="utf-8"), re.M)
        return match.group(1) if match else None
    except OSError:
        return None


def _go_package_path(module, go_module, directories):
    if not go_module or not (module == go_module or module.startswith(go_module + "/")):
        return None
    directory = module[len(go_module):].strip("/") or "."
    return directory if directory in directories else None
