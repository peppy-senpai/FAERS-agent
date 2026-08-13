"""Agents view — port of frontend/src/pages/AgentBuilder.tsx.

Two top-level tabs:
  • Add agent  — build a new agent. The builder itself is split into inner
    tabs (Role, Model, Knowledge Store).
  • My agents  — list every agent saved in the backend database.

We deliberately avoid st.form in the builder: the Model and Knowledge Store
tabs use radio toggles to swap which inputs are shown, and widgets inside a
form don't trigger a rerun until submit, so the conditional fields would never
appear.
"""

from __future__ import annotations

import uuid

import requests
import streamlit as st
from barfi.flow.streamlit import st_flow

from .. import api, graph_blocks, state


def _http_error_detail(exc: requests.HTTPError) -> str:
    """Pull the FastAPI ``detail`` message out of an error response."""
    try:
        return exc.response.json().get("detail", str(exc))
    except (ValueError, AttributeError):
        return str(exc)


def _structured_output_editor(
    key_prefix: str, *, enabled_default: bool, default_value: dict | None
) -> dict | None:
    """Render the optional structured-output field editor.

    Returns a ``{field_name: description}`` dict when enabled and at least one
    named field is given, otherwise ``None`` (free-form text output).
    """
    enabled = st.checkbox(
        "Structured output",
        value=enabled_default,
        help="Have the agent return a structured object with the fields you "
        "define (stored as JSON). Leave off for free-form text.",
        key=key_prefix + "so_on",
    )
    if not enabled:
        return None

    st.caption("Define output fields — a key name and a description of its value.")
    rows = [
        {"key": name, "description": desc}
        for name, desc in (default_value or {}).items()
    ] or [{"key": "", "description": ""}]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",  # gives a trailing "+" row to add more fields
        hide_index=True,
        width="stretch",
        column_config={
            "key": st.column_config.TextColumn(
                "Key name", help="Field name in the output JSON"
            ),
            "description": st.column_config.TextColumn(
                "Value description", help="What this field should contain"
            ),
        },
        key=key_prefix + "so_editor",
    )

    # data_editor may return a list of dicts or a DataFrame depending on input.
    records = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited)
    pairs: dict[str, str] = {}
    for row in records:
        name = (row.get("key") or "").strip()
        if name:
            pairs[name] = (row.get("description") or "").strip()
    return pairs or None


def _tools_multiselect(key: str, *, default_ids: list[str]) -> list[str]:
    """Render a tool picker over the session's available tools.

    Options are every tool from the Tools view (built-ins plus any the user
    added there). Returns the list of selected tool ids. Unknown ids in
    ``default_ids`` (e.g. a tool that was since deleted) are silently dropped so
    the widget doesn't error.
    """
    tools = st.session_state.tools
    if not tools:
        st.info("No tools available yet. Add some in the **Tools** view.")
        return []

    by_id = {t.id: t for t in tools}
    valid_default = [tid for tid in default_ids if tid in by_id]
    selected = st.multiselect(
        "Tools the agent can call",
        options=list(by_id),
        default=valid_default,
        format_func=lambda tid: by_id[tid].name,
        help="Pick the tools this agent is allowed to use. Manage the full "
        "catalogue in the Tools view.",
        key=key,
    )
    # Show each selected tool's one-line summary (not the full Args/Returns).
    for tid in selected:
        st.caption(by_id[tid].description)
    return selected


def render() -> None:
    st.subheader("🤖 Agents")

    tab_add, tab_mine = st.tabs(["➕ Add agent", "📂 My agents"])
    with tab_add:
        _render_add_agent()
    with tab_mine:
        _render_my_agents()


# ─── Add agent ────────────────────────────────────────────


def _render_add_agent() -> None:
    st.caption(
        "Drag blocks onto the canvas and wire them into an orchestrated agent "
        "graph, then Save to compile it to LangGraph code."
    )

    name = st.text_input("Agent name", placeholder="Enter agent name", key="ab_name")
    st.caption(
        "Wire **Input → Agent(s) → Output**. Connect **Tool** blocks into an "
        "agent's *tools* socket; use a **Supervisor** to route between agents."
    )

    # Stable id for this draft graph across reruns.
    graph_id = st.session_state.setdefault("ab_graph_id", uuid.uuid4().hex)

    blocks = graph_blocks.build_blocks(st.session_state.tools)
    response = st_flow(blocks, commands=["save"], key="ab_flow")

    with st.expander("ℹ️ What each block does", expanded=False):
        st.markdown(
            "- **Input** — entry point; the user's message enters the graph here.\n"
            "- **Agent** — an LLM agent. Set its *model* and *system prompt*; wire "
            "**Tool** blocks into its **tools** socket.\n"
            "- **Tool** — pick a tool from the dropdown for an agent to call. "
            "Connect its output to an Agent's **tools** input. Drop one Tool block "
            "per tool.\n"
            "- **Supervisor** — orchestrates multiple agents: it decides which "
            "agent acts next (or finishes). Wire it to the agents it manages.\n"
            "- **Output** — exit point; the final answer leaves the graph here.\n\n"
            "**Typical wiring:** Input → Agent(s) → Output. For multi-agent "
            "routing, use Input → Supervisor → several Agents."
        )

    if response.command != "save":
        return
    if not name.strip():
        st.error("Agent name is required.")
        return

    spec = graph_blocks.normalize(response.editor_schema)
    try:
        result = api.save_graph_agent(graph_id, name.strip(), spec)
    except requests.HTTPError as exc:
        st.error(f"Compile failed: {_http_error_detail(exc)}")
        return
    except requests.RequestException as exc:
        st.error(f"Backend unavailable: {exc}")
        return

    st.success(f"Compiled and saved “{name.strip()}”. See the My agents tab.")
    with st.expander("Generated LangGraph code", expanded=True):
        st.code(result.get("code", ""), language="python")
    # Fresh id for the next graph.
    st.session_state["ab_graph_id"] = uuid.uuid4().hex


# ─── My agents ────────────────────────────────────────────


def _render_my_agents() -> None:
    st.caption("Contents of the `agent_config` table.")

    try:
        agents = api.list_agents()
    except requests.RequestException:
        st.warning("Backend unavailable — can't load saved agents from the database.")
        st.caption(f"Tried {api.base_url()}/agents")
        return

    if not agents:
        st.info("No agents saved yet. Create one in the **Add agent** tab.")
        return

    # Flatten each row for tabular display: list/dict columns become readable
    # strings so the whole agent_config table renders in one grid.
    table_rows = []
    for a in agents:
        ks = a.get("knowledge_store") or {}
        table_rows.append(
            {
                "name": a.get("name"),
                "model": a.get("model"),
                "source": a.get("model_source"),
                "provider": a.get("provider") or "",
                "base_url": a.get("model_url") or "",
                "api_key": "✓" if a.get("has_api_key") else "",
                "structured_output": ", ".join((a.get("structured_output") or {}).keys()),
                "tools": ", ".join(a.get("tools") or []),
                "knowledge_store": ks.get("store_type", "none"),
                "memory": a.get("memory_enabled"),
                "human_in_loop": a.get("human_in_loop"),
                "created_at": a.get("created_at"),
                "id": a.get("id"),
            }
        )

    st.dataframe(table_rows, width="stretch", hide_index=True)

    # Edit control beneath the table.
    st.divider()
    st.markdown("##### Edit an agent")
    edit_by_label = {f"{a['name']} ({a['id'][:8]})": a for a in agents}
    edit_choice = st.selectbox(
        "Select an agent to edit",
        options=list(edit_by_label),
        index=None,
        placeholder="Select an agent to edit…",
        key="my_agents_edit_pick",
    )
    if edit_choice:
        _render_edit_agent(edit_by_label[edit_choice])

    # Delete control beneath the table.
    st.divider()
    by_label = {f"{a['name']} ({a['id'][:8]})": a["id"] for a in agents}
    col_pick, col_btn = st.columns([4, 1])
    choice = col_pick.selectbox(
        "Delete an agent",
        options=list(by_label),
        index=None,
        placeholder="Select an agent to delete…",
        key="my_agents_delete_pick",
    )
    if col_btn.button("🗑 Delete", disabled=choice is None):
        try:
            api.delete_agent(by_label[choice])
        except requests.RequestException:
            st.error("Couldn't delete — backend unavailable.")
        else:
            state.delete_agent(by_label[choice])  # best-effort session cleanup
            st.rerun()


def _render_edit_agent(a: dict) -> None:
    """Pre-filled editable form for an existing agent (upserts by id on save).

    Widget keys are namespaced by agent id so switching the selected agent
    loads that agent's own values instead of leaking state between them.
    """
    aid = a["id"]
    k = f"e_{aid}_"

    name = st.text_input("Agent name", value=a.get("name", ""), key=k + "name")
    system_prompt = st.text_area(
        "System prompt", value=a.get("system_prompt", ""), height=140, key=k + "prompt"
    )
    col_a, col_b = st.columns(2)
    memory_enabled = col_a.checkbox(
        "Memory", value=bool(a.get("memory_enabled", True)), key=k + "mem"
    )
    human_in_loop = col_b.checkbox(
        "Human in the loop", value=bool(a.get("human_in_loop", False)), key=k + "hitl"
    )

    existing_so = a.get("structured_output") or None
    structured_output = _structured_output_editor(
        k, enabled_default=bool(existing_so), default_value=existing_so
    )

    # ─── Model ────────────────────────────────────────────
    is_api = a.get("model_source") == "api"
    source = st.radio(
        "Model source",
        ["Local model", "Online API"],
        index=1 if is_api else 0,
        horizontal=True,
        key=k + "src",
    )
    if source == "Local model":
        model_url = st.text_input(
            "Local URL",
            value=a.get("model_url", "") if not is_api else "",
            placeholder="http://localhost:11434",
            key=k + "lurl",
        )
        model = st.text_input("Model", value=a.get("model", ""), key=k + "lmodel")
        provider = ""
        api_key = ""
    else:
        prov = a.get("provider") or ""
        provider = st.selectbox(
            "Provider",
            state.MODEL_PROVIDERS,
            index=state.MODEL_PROVIDERS.index(prov)
            if prov in state.MODEL_PROVIDERS
            else 0,
            key=k + "prov",
        )
        model_url = st.text_input(
            "Base URL",
            value=a.get("model_url", "") if is_api else "",
            placeholder="https://api.openai.com/v1",
            key=k + "burl",
        )
        model = st.text_input("Model", value=a.get("model", ""), key=k + "amodel")
        api_key = st.text_input(
            "API key",
            type="password",
            placeholder="Leave blank to keep current key"
            if a.get("has_api_key")
            else "sk-…",
            help="Encrypted at rest (Argon2id + AES). Leave blank to keep the current key.",
            key=k + "key",
        )

    # ─── Tools ────────────────────────────────────────────
    selected_tools = _tools_multiselect(k + "tools", default_ids=a.get("tools") or [])

    # ─── Knowledge Store ──────────────────────────────────
    ks = a.get("knowledge_store") or {}
    is_cloud = ks.get("store_type") == "cloud"
    store_choice = st.radio(
        "Vector storage",
        ["Local database", "Cloud database"],
        index=1 if is_cloud else 0,
        horizontal=True,
        key=k + "store",
    )
    location = st.text_input(
        "Local store path" if store_choice == "Local database" else "Connection URL",
        value=ks.get("location", ""),
        key=k + "loc",
    )

    # ─── Save ─────────────────────────────────────────────
    if st.button("Save changes", type="primary", key=k + "save"):
        if not name.strip():
            st.error("Agent name is required.")
            return
        if not model.strip():
            st.error("Model is required.")
            return
        if not model_url.strip():
            label = "Local URL" if source == "Local model" else "Base URL"
            st.error(f"{label} is required.")
            return

        model_src = "local" if source == "Local model" else "api"
        store_type = "local" if store_choice == "Local database" else "cloud"
        knowledge_store = {
            "store_type": store_type,
            "location": location.strip(),
            "files": ks.get("files", []),  # preserve previously indexed files
        }
        try:
            api.create_agent(  # upserts by id → updates the existing row
                api.AgentConfig(
                    id=aid,
                    agent_name=name.strip(),
                    model=model,
                    model_source=model_src,
                    provider=provider,
                    model_url=model_url.strip(),
                    api_key=api_key,  # blank => backend keeps the stored key
                    tools=selected_tools,
                    system_prompt=system_prompt,
                    structured_output=structured_output,
                    knowledge_store=knowledge_store,
                    memory_enabled=memory_enabled,
                    human_in_loop=human_in_loop,
                )
            )
        except requests.RequestException:
            st.error("Backend unavailable — couldn't save changes.")
        else:
            st.success(f"Updated “{name.strip()}”.")
            st.rerun()
