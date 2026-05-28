"""Single-pass LLM analysis that derives architecture from the ingest manifest."""
from __future__ import annotations

from dataclasses import dataclass, field

from llm import complete_json
from ingest import FileInfo

_SYSTEM = (
    "You are a senior software architect. Given a codebase manifest, produce a structured "
    "architectural analysis. Be concise and precise. Respond ONLY with valid JSON."
)

_SCHEMA = """{
  "overview": "2-3 sentence description of what this codebase does and the problem it solves",
  "components": [
    {"name": "ComponentName", "role": "what it does", "files": ["file1.py"]}
  ],
  "layers": [
    {"name": "Layer", "description": "role in the system", "files": ["file.py"]}
  ],
  "data_flow": ["Step 1: ...", "Step 2: ..."],
  "entry_points": ["path/to/main.py - CLI description"],
  "patterns": ["Pattern: description"],
  "external_deps": [{"name": "library", "purpose": "what it is used for"}]
}"""


@dataclass
class ArchitectureAnalysis:
    project_name: str
    overview: str
    components: list[dict] = field(default_factory=list)
    layers: list[dict] = field(default_factory=list)
    data_flow: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    external_deps: list[dict] = field(default_factory=list)

    # also includes local_deps built from manifest (added in analyze())
    local_dep_map: dict = field(default_factory=dict)  # file -> [local files it imports]


class ArchitectureAnalyzer:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def analyze(self, files: list[FileInfo], tree: str, project_name: str) -> ArchitectureAnalysis:
        manifest = _build_manifest(files)
        prompt = (
            f"Project: {project_name}\n\n"
            f"Directory tree:\n{tree}\n\n"
            f"File manifest:\n{manifest}\n\n"
            f"Produce JSON matching this exact schema:\n{_SCHEMA}"
        )
        data = complete_json(self.model, _SYSTEM, prompt, self.api_key)
        local_dep_map = {f.path: f.local_deps for f in files}
        return ArchitectureAnalysis(
            project_name=project_name,
            overview=data.get("overview", ""),
            components=data.get("components", []),
            layers=data.get("layers", []),
            data_flow=data.get("data_flow", []),
            entry_points=data.get("entry_points", []),
            patterns=data.get("patterns", []),
            external_deps=data.get("external_deps", []),
            local_dep_map=local_dep_map,
        )


def _build_manifest(files: list[FileInfo]) -> str:
    lines: list[str] = []
    for f in files:
        lines.append(f"\n### {f.path}  ({f.language}, {f.line_count}L)")
        if f.description:
            lines.append(f"  doc: {f.description.splitlines()[0][:180]}")
        key_imports = _abbreviate_imports(f.imports, f.language)
        if key_imports:
            lines.append(f"  imports: {', '.join(key_imports[:8])}")
        if f.classes:
            lines.append(f"  classes: {', '.join(c.name for c in f.classes)}")
        public_fns = [fn.name for fn in f.functions if not fn.name.startswith("_")]
        if public_fns:
            lines.append(f"  functions: {', '.join(public_fns[:10])}")
    return "\n".join(lines)


def _abbreviate_imports(imports: list[str], lang: str) -> list[str]:
    result: list[str] = []
    _STDLIB = {
        "os", "sys", "re", "json", "typing", "dataclasses", "pathlib",
        "collections", "functools", "itertools", "abc", "copy", "io",
        "struct", "hashlib", "uuid", "enum", "contextlib", "inspect",
        "ast", "subprocess", "threading", "time", "datetime", "math",
    }
    for imp in imports:
        if lang == "Python":
            m = __import__("re").match(r'(?:from|import)\s+([\w.]+)', imp)
            if m:
                mod = m.group(1).split(".")[0]
                if mod not in _STDLIB:
                    result.append(mod)
        else:
            result.append(imp[:40])
    seen: set[str] = set()
    deduped = []
    for r in result:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return deduped
