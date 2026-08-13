"""Load user-uploaded Python files as agent tools.

A custom tool is a ``.py`` file that defines one or more LangChain ``@tool``
functions (i.e. module-level :class:`~langchain_core.tools.BaseTool` instances),
exactly like the built-in ``fetch_records_tool``. This module stores those files,
imports them, and keeps an in-memory registry of the resulting tool objects so
agents can bind them by name.

Security: importing an uploaded module executes arbitrary Python in this process.
That is inherent to "plugin" tools (the same trust model as ComfyUI custom nodes)
and this is intended for a local, single-user deployment. We do lightweight
validation only — the source must compile and must expose at least one
``BaseTool`` — there is no sandbox. Do not expose the upload path to untrusted
callers.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path

from langchain_core.tools import BaseTool

# Where tool files live: the tools package itself, so every tool sits under
# backend/tools/. Overridable via FAERS_TOOLS_DIR, mirroring FAERS_DB_URL.
TOOLS_DIR = Path(os.environ.get("FAERS_TOOLS_DIR", Path(__file__).parent))

# Package modules that live in TOOLS_DIR but are NOT uploadable tools: the
# built-ins (already registered) and the loader/package plumbing. Discovery
# skips these, and an upload may not overwrite them.
RESERVED = {
    "__init__.py",
    "custom_loader.py",
    "disproportionality.py",
    "fetch_records.py",
    "insert_records.py",
    "project_data.py",
}

# name -> tool object, for every successfully loaded custom tool.
_CUSTOM: dict[str, BaseTool] = {}
# name -> source file path, so a tool can be deleted off disk by name.
_PATHS: dict[str, str] = {}


def _ensure_dir() -> None:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)


def load_tool_file(path: str | os.PathLike[str]) -> list[BaseTool]:
    """Import a tool file and return the ``BaseTool`` objects it defines.

    Raises :class:`ValueError` if the file doesn't compile or exposes no tool,
    so the caller can turn that into a clean client error rather than a crash.
    """
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    try:
        compile(source, str(path), "exec")  # surface syntax errors up front
    except SyntaxError as exc:
        raise ValueError(f"Syntax error: {exc}") from exc

    # Unique module name so re-uploads don't collide in sys.modules.
    module_name = f"faers_custom_tool_{path.stem}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load module from {path.name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)  # runs the uploaded code
    except Exception as exc:  # noqa: BLE001 - any import-time error is user's
        sys.modules.pop(module_name, None)
        raise ValueError(f"Import failed: {exc}") from exc

    tools = [obj for obj in vars(module).values() if isinstance(obj, BaseTool)]
    if not tools:
        sys.modules.pop(module_name, None)
        raise ValueError(
            "No tool found. Define a function decorated with LangChain's @tool."
        )
    return tools


def register_file(path: str | os.PathLike[str]) -> list[BaseTool]:
    """Load a file and add its tools to the in-memory registry."""
    tools = load_tool_file(path)
    for tool in tools:
        _CUSTOM[tool.name] = tool
        _PATHS[tool.name] = str(path)
    return tools


def unregister(name: str) -> None:
    """Drop a tool from the in-memory registry (no-op if absent)."""
    _CUSTOM.pop(name, None)
    _PATHS.pop(name, None)


def path_for(name: str) -> str | None:
    """Source file path of a registered custom tool, if known."""
    return _PATHS.get(name)


def is_custom(name: str) -> bool:
    return name in _CUSTOM


def custom_tools() -> list[BaseTool]:
    """All currently registered custom tools."""
    return list(_CUSTOM.values())


def discover_all() -> None:
    """Load every ``.py`` file under :data:`TOOLS_DIR` (called at startup).

    A single bad file is skipped with a warning rather than aborting discovery
    of the rest.
    """
    _ensure_dir()
    for file in sorted(TOOLS_DIR.glob("*.py")):
        # Skip built-ins/plumbing and any leftover ".tmp_*" upload staging files.
        if file.name in RESERVED or file.name.startswith("."):
            continue
        try:
            register_file(file)
        except ValueError as exc:  # pragma: no cover - defensive at startup
            print(f"Skipping custom tool {file.name}: {exc}")
