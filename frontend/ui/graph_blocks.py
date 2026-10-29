"""barfi blocks for the visual agent-graph builder + schema normalization.

Defines the palette the user drags onto the canvas — Input, Agent, Supervisor,
Output, and one Tool block per registered tool — and normalizes the barfi
``FlowSchema`` the canvas returns into the compact spec the backend compiler
expects (``{nodes: [{id, type, data}], edges: [{source, target, target_interface}]}``).

Blocks only declare sockets + option widgets; they have no compute function —
execution is LangGraph's job once the graph is compiled server-side.
"""

from __future__ import annotations

from typing import Any

from barfi.flow import Block

# Block names that map to node types.
_INPUT = "Input"
_OUTPUT = "Output"
_AGENT = "Agent"
_SUPERVISOR = "Supervisor"
_TOOL = "Tool"


# Option fields shown on Agent/Supervisor blocks: (label shown on the block,
# canonical key the compiler reads, widget type, default, select items).
_MODEL_OPTION_SPECS = [
    ("Model (e.g. claude-opus-4-8)", "model", "input", "claude-opus-4-8", None),
    ("Model source (api or local)", "model_source", "select", "api", ["api", "local"]),
    ("Provider (e.g. anthropic)", "provider", "input", "anthropic", None),
    ("Base URL (e.g. http://localhost:11434)", "model_url", "input", "", None),
    ("System prompt (e.g. You are a FAERS analyst)", "system_prompt", "input", "", None),
]

# Map the friendly labels back to the keys the backend compiler expects.
_LABEL_TO_KEY = {label: key for label, key, *_ in _MODEL_OPTION_SPECS}


def _model_options(block: Block) -> None:
    """Add the shared model-config options to an Agent/Supervisor block."""
    for label, _key, wtype, default, items in _MODEL_OPTION_SPECS:
        if items is not None:
            block.add_option(name=label, type=wtype, items=items, value=default)
        else:
            block.add_option(name=label, type=wtype, value=default)


def build_blocks(tools: list) -> list[Block]:
    """Build the block palette. ``tools`` are ``state.Tool`` objects."""
    blocks: list[Block] = []

    inp = Block(name=_INPUT)
    inp.add_output(name="state")
    blocks.append(inp)

    agent = Block(name=_AGENT)
    agent.add_input(name="in")
    agent.add_input(name="tools")
    agent.add_output(name="out")
    _model_options(agent)
    blocks.append(agent)

    supervisor = Block(name=_SUPERVISOR)
    supervisor.add_input(name="in")
    supervisor.add_output(name="out")
    _model_options(supervisor)
    blocks.append(supervisor)

    out = Block(name=_OUTPUT)
    out.add_input(name="in")
    blocks.append(out)

    # A single Tool block with a dropdown of every registered tool. Drop one per
    # tool an agent should use and wire its output into the agent's "tools" input.
    tool_ids = [t.id for t in tools]
    tb = Block(name=_TOOL)
    tb.add_output(name="tool")
    tb.add_option(
        name="tool_id",
        type="select",
        items=tool_ids,
        value=tool_ids[0] if tool_ids else "",
    )
    blocks.append(tb)

    return blocks


def _canonical(opts: dict[str, Any]) -> dict[str, Any]:
    """Map the friendly option labels back to the compiler's canonical keys."""
    return {_LABEL_TO_KEY.get(name, name): value for name, value in opts.items()}


def normalize(schema: Any) -> dict[str, Any]:
    """Convert a barfi ``FlowSchema`` into the backend's graph spec."""
    nodes: list[dict[str, Any]] = []
    for n in schema.nodes:
        opts = {o.name: o.value for o in n.options}
        node_type = n.type
        if node_type == _INPUT:
            nodes.append({"id": n.id, "type": "input"})
        elif node_type == _OUTPUT:
            nodes.append({"id": n.id, "type": "output"})
        elif node_type == _AGENT:
            nodes.append({"id": n.id, "type": "agent", "data": _canonical(opts)})
        elif node_type == _SUPERVISOR:
            nodes.append({"id": n.id, "type": "supervisor", "data": _canonical(opts)})
        elif node_type == _TOOL:
            # Tool block: the chosen tool id comes from the dropdown option.
            nodes.append(
                {"id": n.id, "type": "tool", "data": {"tool_id": opts.get("tool_id", "")}}
            )

    edges: list[dict[str, Any]] = []
    for c in schema.connections:
        edges.append(
            {
                "source": c.outputNode,
                "target": c.inputNode,
                "target_interface": c.inputNodeInterface,
            }
        )

    return {"nodes": nodes, "edges": edges}
