"""Parse a repository and extract structural metadata for each source file."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from config import IGNORE_DIRS, IGNORE_EXTENSIONS, TEXT_EXTENSIONS, MAX_FILE_SIZE_KB
except ImportError:
    IGNORE_DIRS = {
        ".venv", "node_modules", ".git", "repos", "build", "dist",
        "__pycache__", ".idea", ".mypy_cache", "coverage", ".pytest_cache",
        "target", "vendor", "tmp", "temp", ".next", ".nuxt", "out", ".tox",
    }
    IGNORE_EXTENSIONS = {
        ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".webp",
        ".mp4", ".mp3", ".wav", ".pdf", ".zip", ".tar", ".gz", ".whl",
        ".lock", ".sum",
    }
    TEXT_EXTENSIONS = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
        ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".hpp", ".swift",
        ".kt", ".scala", ".sh", ".bash", ".sql", ".yaml", ".yml",
        ".toml", ".json", ".xml", ".html", ".css", ".scss", ".md",
        ".txt", ".env", ".cfg", ".ini", ".conf", ".r",
    }
    MAX_FILE_SIZE_KB = 500


@dataclass
class MethodInfo:
    name: str
    args: str
    docstring: str = ""


@dataclass
class ClassInfo:
    name: str
    docstring: str = ""
    methods: list[MethodInfo] = field(default_factory=list)


@dataclass
class FunctionInfo:
    name: str
    args: str
    docstring: str = ""


@dataclass
class FileInfo:
    path: str           # relative to repo root, forward slashes
    language: str
    line_count: int
    char_count: int     # raw character count for token estimation
    description: str    # module docstring or first comment block
    imports: list[str] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    is_entry_point: bool = False
    local_deps: list[str] = field(default_factory=list)  # resolved local file paths


LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".h": "C/C++Header", ".hpp": "C++",
    ".swift": "Swift", ".kt": "Kotlin", ".scala": "Scala",
    ".sh": "Shell", ".bash": "Shell", ".sql": "SQL",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".json": "JSON", ".md": "Markdown", ".html": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".xml": "XML",
}

ENTRY_POINT_NAMES = {
    "main.py", "app.py", "server.py", "cli.py", "run.py", "wsgi.py",
    "index.js", "index.ts", "app.js", "server.js", "main.go", "main.rs",
}


class RepoIngestor:
    def __init__(self, root_dir: str):
        self.root = Path(root_dir).resolve()
        self._py_parser = None
        self._py_lang = None
        self._init_treesitter()

    def _init_treesitter(self):
        import warnings
        # Try tree-sitter-languages bundle first (single install, all grammars)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from tree_sitter_languages import get_parser
                self._py_parser = get_parser("python")
            return
        except Exception:
            pass
        # Fallback: standalone tree-sitter-python package
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                import tree_sitter_python as tspython
                from tree_sitter import Language, Parser
                self._py_parser = Parser(Language(tspython.language()))
        except Exception:
            pass

    def scan(self) -> tuple[list[FileInfo], str]:
        """Return (files, annotated_tree_string). local_deps on each FileInfo is populated here."""
        files: list[FileInfo] = []
        for path in self._walk():
            try:
                fi = self._extract(path)
                if fi:
                    files.append(fi)
            except Exception:
                pass
        self._populate_local_deps(files)
        return files, self._build_tree()

    def _populate_local_deps(self, files: list[FileInfo]):
        from relationships import resolve_import_graph
        rels = resolve_import_graph(files)
        dep_map: dict[str, list[str]] = {}
        for r in rels:
            dep_map.setdefault(r.source, []).append(r.target)
        for f in files:
            f.local_deps = dep_map.get(f.path, [])

    # ------------------------------------------------------------------
    # Filesystem walk
    # ------------------------------------------------------------------

    def _walk(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in IGNORE_DIRS and not d.startswith(".")
            )
            for fname in sorted(filenames):
                ext = Path(fname).suffix.lower()
                if ext in IGNORE_EXTENSIONS:
                    continue
                if ext not in TEXT_EXTENSIONS:
                    continue
                fpath = Path(dirpath) / fname
                try:
                    if fpath.stat().st_size > MAX_FILE_SIZE_KB * 1024:
                        continue
                except OSError:
                    continue
                yield fpath

    # ------------------------------------------------------------------
    # Per-file extraction
    # ------------------------------------------------------------------

    def _extract(self, path: Path) -> Optional[FileInfo]:
        ext = path.suffix.lower()
        lang = LANGUAGE_MAP.get(ext, "Text")
        rel = str(path.relative_to(self.root)).replace("\\", "/")

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        line_count = content.count("\n") + 1

        if lang == "Python" and self._py_parser:
            info = self._parse_python_ts(content)
        elif lang == "Python":
            info = self._parse_python_re(content)
        elif lang in ("JavaScript", "TypeScript"):
            info = self._parse_js(content)
        elif lang == "Go":
            info = self._parse_go(content)
        elif lang == "Rust":
            info = self._parse_rust(content)
        else:
            info = {}

        is_entry = Path(rel).name in ENTRY_POINT_NAMES

        return FileInfo(
            path=rel,
            language=lang,
            line_count=line_count,
            char_count=len(content),
            description=info.get("description", ""),
            imports=info.get("imports", []),
            classes=info.get("classes", []),
            functions=info.get("functions", []),
            is_entry_point=is_entry,
        )

    # ------------------------------------------------------------------
    # Python via Tree-sitter
    # ------------------------------------------------------------------

    def _parse_python_ts(self, content: str) -> dict:
        tree = self._py_parser.parse(content.encode())
        root = tree.root_node

        description = ""
        imports: list[str] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []

        for child in root.children:
            t = child.type
            if not description and t == "expression_statement":
                s = child.children[0] if child.children else None
                if s and s.type in ("string", "concatenated_string"):
                    description = self._ts_str(content, s)
            elif t in ("import_statement", "import_from_statement"):
                imports.append(content[child.start_byte:child.end_byte].split("\n")[0].strip())
            elif t == "class_definition":
                classes.append(self._ts_class(content, child))
            elif t == "function_definition":
                functions.append(self._ts_func(content, child))
            elif t == "decorated_definition":
                for sub in child.children:
                    if sub.type == "class_definition":
                        classes.append(self._ts_class(content, sub))
                    elif sub.type == "function_definition":
                        functions.append(self._ts_func(content, sub))

        return {"description": description, "imports": imports, "classes": classes, "functions": functions}

    def _ts_str(self, src: str, node) -> str:
        raw = src[node.start_byte:node.end_byte].strip()
        for q in ('"""', "'''", '"', "'"):
            if raw.startswith(q) and raw.endswith(q) and len(raw) > 2 * len(q):
                return raw[len(q):-len(q)].strip()[:300]
        return raw.strip("\"'")[:300]

    def _ts_class(self, src: str, node) -> ClassInfo:
        name = ""
        docstring = ""
        methods: list[MethodInfo] = []
        for child in node.children:
            if child.type == "identifier":
                name = src[child.start_byte:child.end_byte]
            elif child.type == "block":
                first = True
                for stmt in child.children:
                    if stmt.type == "expression_statement" and first:
                        s = stmt.children[0] if stmt.children else None
                        if s and s.type in ("string", "concatenated_string"):
                            docstring = self._ts_str(src, s)
                        first = False
                    elif stmt.type == "function_definition":
                        methods.append(self._ts_func(src, stmt))
                    elif stmt.type == "decorated_definition":
                        for sub in stmt.children:
                            if sub.type == "function_definition":
                                methods.append(self._ts_func(src, sub))
        return ClassInfo(name=name, docstring=docstring, methods=methods)

    def _ts_func(self, src: str, node) -> FunctionInfo:
        name = ""
        args = ""
        docstring = ""
        for child in node.children:
            if child.type == "identifier":
                name = src[child.start_byte:child.end_byte]
            elif child.type == "parameters":
                args = src[child.start_byte:child.end_byte]
                if len(args) > 60:
                    args = args[:57] + "..."
            elif child.type == "block":
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        s = stmt.children[0] if stmt.children else None
                        if s and s.type in ("string", "concatenated_string"):
                            docstring = self._ts_str(src, s)
                        break
        return FunctionInfo(name=name, args=args, docstring=docstring)

    # ------------------------------------------------------------------
    # Python via regex (fallback)
    # ------------------------------------------------------------------

    def _parse_python_re(self, src: str) -> dict:
        description = ""
        m = re.match(r'\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')', src, re.DOTALL)
        if m:
            description = (m.group(1) or m.group(2) or "").strip()[:300]

        imports = re.findall(r'^(?:import|from)\s+.+', src, re.MULTILINE)
        classes = [ClassInfo(name=m) for m in re.findall(r'^class\s+(\w+)', src, re.MULTILINE)]
        functions = [
            FunctionInfo(name=m[0], args=f"({m[1][:50]})")
            for m in re.findall(r'^def\s+(\w+)\(([^)]*)\)', src, re.MULTILINE)
        ]
        return {"description": description, "imports": imports, "classes": classes, "functions": functions}

    # ------------------------------------------------------------------
    # JavaScript / TypeScript
    # ------------------------------------------------------------------

    def _parse_js(self, src: str) -> dict:
        imports = (
            re.findall(r'^import\s+.+', src, re.MULTILINE) +
            re.findall(r'^(?:const|let|var)\s+\w+\s*=\s*require\(.+\)', src, re.MULTILINE)
        )
        classes = [ClassInfo(name=m) for m in re.findall(r'(?:export\s+)?class\s+(\w+)', src)]
        fns: list[FunctionInfo] = []
        for m in re.finditer(
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)|'
            r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>',
            src
        ):
            name = m.group(1) or m.group(3)
            args = (m.group(2) or m.group(4) or "")[:50]
            if name:
                fns.append(FunctionInfo(name=name, args=f"({args})"))
        return {"description": "", "imports": imports[:20], "classes": classes, "functions": fns}

    # ------------------------------------------------------------------
    # Go
    # ------------------------------------------------------------------

    def _parse_go(self, src: str) -> dict:
        m = re.search(r'^package\s+(\w+)', src, re.MULTILINE)
        pkg = m.group(1) if m else ""
        imports = re.findall(r'"([^"]+)"', src)[:20]
        classes = [
            ClassInfo(name=m)
            for m in re.findall(r'type\s+(\w+)\s+(?:struct|interface)', src)
        ]
        fns = [
            FunctionInfo(name=m[0], args=f"({m[1][:50]})")
            for m in re.findall(r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(([^)]*)\)', src)
        ]
        return {
            "description": f"Package: {pkg}" if pkg else "",
            "imports": imports,
            "classes": classes,
            "functions": fns,
        }

    # ------------------------------------------------------------------
    # Rust
    # ------------------------------------------------------------------

    def _parse_rust(self, src: str) -> dict:
        imports = re.findall(r'^use\s+(.+);', src, re.MULTILINE)[:20]
        classes = [
            ClassInfo(name=m)
            for m in re.findall(r'(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)', src)
        ]
        fns = [
            FunctionInfo(name=m[0], args=f"({m[1][:50]})")
            for m in re.findall(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(([^)]*)\)', src)
        ]
        return {"description": "", "imports": imports, "classes": classes, "functions": fns}

    # ------------------------------------------------------------------
    # Directory tree
    # ------------------------------------------------------------------

    def _build_tree(self) -> str:
        lines = [f"{self.root.name}/"]
        self._tree_recurse(self.root, "", lines, depth=0)
        return "\n".join(lines)

    def _tree_recurse(self, dir_path: Path, prefix: str, lines: list, depth: int):
        if depth > 6:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        entries = [e for e in entries if not e.name.startswith(".") and e.name not in IGNORE_DIRS]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "`-- " if is_last else "+-- "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                ext = "    " if is_last else "|   "
                self._tree_recurse(entry, prefix + ext, lines, depth + 1)
