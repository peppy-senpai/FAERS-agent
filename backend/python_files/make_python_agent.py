"""Write generated LangChain agent variables into ``python_agent.py``."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


PYTHON_AGENT_FILE = Path(__file__).with_name("python_agent.py")
_GENERATED_HEADER = "# Generated agent variables are written below by make_python_agent.py."


def _variable_name(agent_id: str) -> str:
    safe_id = re.sub(r"\W+", "_", agent_id).strip("_")
    if not safe_id or safe_id[0].isdigit():
        safe_id = f"_{safe_id}"
    return f"agent_{safe_id}"


def _block_markers(agent_id: str) -> tuple[str, str]:
    return (
        f"# <generated-agent id={agent_id}>",
        f"# </generated-agent id={agent_id}>",
    )


def _agent_block(config: dict[str, Any]) -> str:
    agent_id = str(config["id"])
    variable_name = _variable_name(agent_id)
    start, end = _block_markers(agent_id)
    structured_output = config.get("structured_output")

    return "\n".join(
        [
            start,
            f"{variable_name} = create_agent(",
            "    model=_chat_model(",
            f"        agent_id={agent_id!r},",
            f"        model={config.get('model', '')!r},",
            f"        model_source={config.get('model_source', 'local')!r},",
            f"        provider={config.get('provider', '')!r},",
            f"        model_url={config.get('model_url', '')!r},",
            "    ),",
            f"    tools=_selected_tools({list(config.get('tools') or [])!r}),",
            f"    system_prompt={config.get('system_prompt', '')!r},",
            f"    checkpointer=_checkpointer({bool(config.get('memory_enabled', True))!r}),",
            "    response_format=_response_format(",
            f"        {agent_id!r},",
            f"        {structured_output!r},",
            "    ),",
            ")",
            end,
            "",
        ]
    )


def write_agent_variable(config: dict[str, Any]) -> str:
    """Create or replace ``agent_<agent_id> = create_agent(...)`` in the file."""
    agent_id = str(config.get("id") or "").strip()
    if not agent_id:
        raise ValueError("Agent config must include an id before code generation.")

    source = PYTHON_AGENT_FILE.read_text(encoding="utf-8")
    block = _agent_block({**config, "id": agent_id})
    start, end = _block_markers(agent_id)
    pattern = re.compile(
        rf"\n?{re.escape(start)}\n.*?\n{re.escape(end)}\n?",
        flags=re.DOTALL,
    )

    if pattern.search(source):
        source = pattern.sub(f"\n{block}", source)
    else:
        if _GENERATED_HEADER not in source:
            source = source.rstrip() + f"\n\n{_GENERATED_HEADER}\n"
        source = source.rstrip() + f"\n\n{block}"

    PYTHON_AGENT_FILE.write_text(source, encoding="utf-8")
    return _variable_name(agent_id)
