"""Agent Builder view — port of frontend/src/pages/AgentBuilder.tsx."""

from __future__ import annotations

import requests
import streamlit as st

from .. import api, state


def render() -> None:
    st.subheader("🤖 Add Agent")
    st.caption("Configure an agent and the FAERS tools it can use.")

    with st.form("agent_builder", clear_on_submit=False):
        name = st.text_input("Agent name", placeholder="FAERS Safety Analyst")
        model = st.selectbox("Model", state.MODELS, index=0)
        system_prompt = st.text_area(
            "System prompt",
            placeholder="You are a pharmacovigilance analyst…",
            height=120,
        )

        st.markdown("**Tools**")
        selected_tools: list[str] = []
        for t in st.session_state.tools:
            if st.checkbox(f"{t.name} — {t.description}", key=f"ab_tool_{t.id}"):
                selected_tools.append(t.id)

        col_a, col_b = st.columns(2)
        memory_enabled = col_a.checkbox("Memory", value=True)
        human_in_loop = col_b.checkbox("Human in the loop", value=False)

        submitted = st.form_submit_button("Create agent", type="primary")

    if submitted:
        if not name.strip():
            st.error("Agent name is required.")
            return

        state.add_agent(
            state.Agent(
                name=name.strip(),
                model=model,
                system_prompt=system_prompt,
                tools=selected_tools,
                memory_enabled=memory_enabled,
                human_in_loop=human_in_loop,
            )
        )

        # Best-effort: tell the backend to build the runtime agent too.
        try:
            api.create_agent(
                api.AgentConfig(
                    agent_name=name.strip(),
                    model=model,
                    tools=selected_tools,
                    system_prompt=system_prompt,
                    memory_enabled=memory_enabled,
                    human_in_loop=human_in_loop,
                )
            )
        except requests.RequestException:
            pass  # backend optional during development

        st.success(f"Created agent “{name.strip()}”.")
        st.session_state.view = "chat"
        st.rerun()

    # Existing agents
    st.divider()
    st.markdown("##### Your agents")
    agents = st.session_state.agents
    for a in agents:
        col_info, col_del = st.columns([6, 1])
        col_info.markdown(f"**{a.name}**  \n{a.model} · {len(a.tools)} tools")
        if col_del.button(
            "🗑",
            key=f"del_agent_{a.id}",
            disabled=len(agents) == 1,
            help="Delete agent",
        ):
            state.delete_agent(a.id)
            st.rerun()
