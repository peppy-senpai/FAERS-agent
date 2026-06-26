"""Agents view — port of frontend/src/pages/AgentBuilder.tsx.

Two top-level tabs:
  • Add agent  — build a new agent. The builder itself is split into four
    inner tabs (Role, Model, Knowledge Store, Tools).
  • My agents  — list every agent saved in the backend database.

We deliberately avoid st.form in the builder: the Model and Knowledge Store
tabs use radio toggles to swap which inputs are shown, and widgets inside a
form don't trigger a rerun until submit, so the conditional fields would never
appear.
"""

from __future__ import annotations

import requests
import streamlit as st

from .. import api, state


def render() -> None:
    st.subheader("🤖 Agents")

    tab_add, tab_mine = st.tabs(["➕ Add agent", "📂 My agents"])
    with tab_add:
        _render_add_agent()
    with tab_mine:
        _render_my_agents()


# ─── Add agent ────────────────────────────────────────────


def _render_add_agent() -> None:
    st.caption("Configure an agent and the FAERS tools it can use.")

    name = st.text_input(
        "Agent name",
        placeholder="Enter agent name",
        key="ab_name",
    )

    tab_role, tab_model, tab_knowledge, tab_tools = st.tabs(
        ["📝 Role", "🧠 Model", "📚 Knowledge Store", "🔧 Tools"]
    )

    # ─── Role ─────────────────────────────────────────────
    with tab_role:
        st.markdown("Describe what this agent does and how it should behave.")
        system_prompt = st.text_area(
            "System prompt",
            placeholder="Enter prompt describing role of agent",
            height=180,
            key="ab_system_prompt",
        )
        col_a, col_b = st.columns(2)
        memory_enabled = col_a.checkbox("Memory", value=True, key="ab_memory")
        human_in_loop = col_b.checkbox(
            "Human in the loop", value=False, key="ab_hitl"
        )

    # ─── Model ────────────────────────────────────────────
    with tab_model:
        model_source = st.radio(
            "Model source",
            ["Local model", "Online API"],
            horizontal=True,
            key="ab_model_source",
        )
        if model_source == "Local model":
            model = st.selectbox("Local model", state.MODELS, index=0, key="ab_model")
            provider = ""
            model_url = ""
            api_key = ""
        else:
            provider = st.selectbox(
                "Provider",
                state.MODEL_PROVIDERS,
                index=0,
                help="LangChain/LangGraph chat-model provider wrapper.",
                key="ab_provider",
            )
            model_url = st.text_input(
                "Base URL",
                placeholder="https://api.openai.com/v1",
                key="ab_model_url",
            )
            model = st.text_input(
                "Model",
                placeholder="gpt-4o-mini",
                key="ab_model_name",
            )
            api_key = st.text_input(
                "API key",
                type="password",
                placeholder="sk-…",
                key="ab_api_key",
            )

    # ─── Knowledge Store ──────────────────────────────────
    with tab_knowledge:
        store_choice = st.radio(
            "Vector storage",
            ["Local database", "Cloud database"],
            horizontal=True,
            key="ab_store_choice",
        )
        if store_choice == "Local database":
            location = st.text_input(
                "Local store path",
                placeholder="./data/chroma",
                key="ab_store_local_path",
            )
        else:
            location = st.text_input(
                "Connection URL",
                placeholder="https://my-index.pinecone.io",
                key="ab_store_cloud_url",
            )

        uploads = st.file_uploader(
            "Upload local files to index",
            accept_multiple_files=True,
            type=["pdf", "txt", "csv", "md", "json", "py"],
            key="ab_store_files",
        )
        uploaded_names = [f.name for f in uploads] if uploads else []
        if uploaded_names:
            st.caption(f"{len(uploaded_names)} file(s): " + ", ".join(uploaded_names))

    # ─── Tools ────────────────────────────────────────────
    with tab_tools:
        tool_by_id = {t.id: t for t in st.session_state.tools}
        selected_tools = st.multiselect(
            "Tools this agent can access",
            options=list(tool_by_id),
            format_func=lambda tid: tool_by_id[tid].name,
            key="ab_tools",
        )
        for tid in selected_tools:
            st.caption(f"• {tool_by_id[tid].name} — {tool_by_id[tid].description}")

    # ─── Submit ───────────────────────────────────────────
    st.divider()
    if st.button("Create agent", type="primary"):
        if not name.strip():
            st.error("Agent name is required.")
            return

        store_type = "local" if store_choice == "Local database" else "cloud"
        knowledge_store = state.KnowledgeStore(
            store_type=store_type,
            location=location.strip(),
            files=uploaded_names,
        )
        model_src = "local" if model_source == "Local model" else "api"

        new_agent = state.Agent(
            name=name.strip(),
            model=model,
            model_source=model_src,
            provider=provider,
            model_url=model_url.strip(),
            api_key=api_key,
            system_prompt=system_prompt,
            tools=selected_tools,
            knowledge_store=knowledge_store,
            memory_enabled=memory_enabled,
            human_in_loop=human_in_loop,
        )
        state.add_agent(new_agent)

        # Persist to the backend database. Surface failures so the user knows
        # whether the agent was actually saved.
        try:
            api.create_agent(
                api.AgentConfig(
                    id=new_agent.id,
                    agent_name=new_agent.name,
                    model=model,
                    model_source=model_src,
                    provider=provider,
                    model_url=model_url.strip(),
                    api_key=api_key,
                    tools=selected_tools,
                    system_prompt=system_prompt,
                    knowledge_store=knowledge_store.model_dump(),
                    memory_enabled=memory_enabled,
                    human_in_loop=human_in_loop,
                )
            )
            st.success(f"Created agent “{new_agent.name}”. See the My agents tab.")
        except requests.RequestException:
            st.warning(
                f"Created “{new_agent.name}” locally, but the backend was "
                "unavailable so it wasn't saved to the database."
            )


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
                "tools": ", ".join(a.get("tools") or []),
                "knowledge_store": ks.get("store_type", "none"),
                "memory": a.get("memory_enabled"),
                "human_in_loop": a.get("human_in_loop"),
                "created_at": a.get("created_at"),
                "id": a.get("id"),
            }
        )

    st.dataframe(table_rows, width="stretch", hide_index=True)

    # Delete control beneath the table.
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
