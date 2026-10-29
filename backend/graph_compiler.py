"""Compile a visual node-graph spec into LangGraph ``StateGraph`` code.

The frontend's barfi canvas produces a normalized spec::

    {
      "nodes": [
        {"id": "..", "type": "input"},
        {"id": "..", "type": "agent",
         "data": {"model": "..", "model_source": "..", "provider": "..",
                  "model_url": "..", "system_prompt": ".."}},
        {"id": "..", "type": "tool", "data": {"tool_id": "reporting_odds_ratio"}},
        {"id": "..", "type": "supervisor", "data": {"model": "..", ...}},
        {"id": "..", "type": "output"}
      ],
      "edges": [{"source": "..", "target": "..", "target_interface": "in|tools"}]
    }

:func:`compile_graph` validates it and emits a ``build_agent_<id>()`` function
that assembles a :class:`~langgraph.graph.StateGraph`, reusing the runtime
helpers already in :mod:`backend.python_files.python_agent` (``_chat_model``,
``_selected_tools``, ``_checkpointer``, ``_supervisor_node``). The generated
source is written into ``python_agent.py`` by
:func:`backend.python_files.make_python_agent.write_graph_builder` and executed
later to run the agent.

Two topologies are supported: a linear agent pipeline (Input → Agent(s) →
Output) and a supervisor fanning out to worker agents (Input → Supervisor →
{Agents}).
"""

from __future__ import annotations

import re
from typing import Any


def graph_builder_name(agent_id: str) -> str:
    safe = re.sub(r"\W+", "_", str(agent_id)).strip("_")
    if not safe or safe[0].isdigit():
        safe = f"_{safe}"
    return f"build_agent_{safe}"


def _node_key(node_id: str) -> str:
    safe = re.sub(r"\W+", "_", str(node_id)).strip("_")
    return f"n_{safe or 'x'}"


def _chat_model_call(agent_id: str, data: dict[str, Any]) -> str:
    return (
        "_chat_model("
        f"agent_id={agent_id!r}, "
        f"model={data.get('model', '')!r}, "
        f"model_source={data.get('model_source', 'local')!r}, "
        f"provider={data.get('provider', '')!r}, "
        f"model_url={data.get('model_url', '')!r})"
    )


def _validate(nodes, inputs, outputs, agents, supervisors) -> None:
    if len(inputs) != 1:
        raise ValueError("Graph needs exactly one Input block.")
    if len(outputs) != 1:
        raise ValueError("Graph needs exactly one Output block.")
    if not agents and not supervisors:
        raise ValueError("Graph needs at least one Agent block.")
    for a in agents:
        if not (a.get("data") or {}).get("model"):
            raise ValueError("Every Agent block needs a model.")


def compile_graph(agent_id: str, spec: dict[str, Any], *, memory_enabled: bool = True) -> str:
    """Return LangGraph source for ``build_agent_<id>()`` from a graph spec."""
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    by_id = {n["id"]: n for n in nodes}

    inputs = [n for n in nodes if n["type"] == "input"]
    outputs = [n for n in nodes if n["type"] == "output"]
    agents = [n for n in nodes if n["type"] == "agent"]
    supervisors = [n for n in nodes if n["type"] == "supervisor"]
    _validate(nodes, inputs, outputs, agents, supervisors)

    input_id = inputs[0]["id"]
    output_id = outputs[0]["id"]

    # Tools bound to each agent: tool blocks wired into the agent's "tools" input.
    tools_by_agent: dict[str, list[str]] = {}
    for e in edges:
        if e.get("target_interface") == "tools":
            src = by_id.get(e["source"])
            if src and src["type"] == "tool":
                tid = (src.get("data") or {}).get("tool_id")
                if tid:
                    tools_by_agent.setdefault(e["target"], []).append(tid)

    # Flow edges are everything that isn't a tool binding.
    flow = [e for e in edges if e.get("target_interface") != "tools"]

    # Workers of each supervisor: nodes the supervisor points at.
    workers_by_sup: dict[str, list[str]] = {}
    for e in flow:
        if by_id.get(e["source"], {}).get("type") == "supervisor":
            workers_by_sup.setdefault(e["source"], []).append(e["target"])

    body: list[str] = ["    g = StateGraph(MessagesState)", ""]

    # Node definitions.
    for a in agents:
        key = _node_key(a["id"])
        data = a.get("data") or {}
        tool_ids = tools_by_agent.get(a["id"], [])
        body += [
            f"    {key} = create_agent(",
            f"        model={_chat_model_call(agent_id, data)},",
            f"        tools=_selected_tools({tool_ids!r}),",
            f"        system_prompt={data.get('system_prompt', '')!r},",
            "    )",
            f"    g.add_node({key!r}, {key})",
        ]
    for s in supervisors:
        key = _node_key(s["id"])
        data = s.get("data") or {}
        worker_keys = [_node_key(w) for w in workers_by_sup.get(s["id"], [])]
        body += [
            f"    g.add_node({key!r}, _supervisor_node(",
            f"        model={_chat_model_call(agent_id, data)},",
            f"        system_prompt={data.get('system_prompt', '')!r},",
            f"        workers={worker_keys!r},",
            "    ))",
        ]

    body.append("")

    # Edges.
    for e in flow:
        src, tgt = e["source"], e["target"]
        src_node, tgt_node = by_id.get(src, {}), by_id.get(tgt, {})
        if src == input_id:
            body.append(f"    g.add_edge(START, {_node_key(tgt)!r})")
        elif tgt == output_id:
            body.append(f"    g.add_edge({_node_key(src)!r}, END)")
        elif src_node.get("type") == "supervisor":
            # Supervisor routes to workers via Command; add the return edge so
            # control loops back to the supervisor after each worker runs.
            body.append(f"    g.add_edge({_node_key(tgt)!r}, {_node_key(src)!r})")
        else:
            body.append(f"    g.add_edge({_node_key(src)!r}, {_node_key(tgt)!r})")

    body += [
        "",
        f"    return g.compile(checkpointer=_checkpointer({bool(memory_enabled)!r}))",
    ]

    header = f"def {graph_builder_name(agent_id)}():"
    return header + "\n" + "\n".join(body) + "\n"
