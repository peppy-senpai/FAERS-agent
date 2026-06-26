"""FAERS Agent — Streamlit frontend entry point.

Replaces the React App/Layout/Sidebar. Run with:

    streamlit run frontend/app.py
"""

from __future__ import annotations

import streamlit as st

from ui import state
from ui.views import agent_builder, project, settings, tools

st.set_page_config(page_title="FAERS Agent", page_icon="📊", layout="wide")

state.init_state()


def _sidebar() -> None:
    with st.sidebar:
        # Brand
        st.markdown("### 📊 FAERS Agent")
        st.caption("Safety signal studio")

        # New project
        if st.button("➕  New Project", use_container_width=True, type="primary"):
            state.create_project()
            st.session_state.view = "projects"
            st.rerun()

        # Nav
        nav = {
            "agents": "🤖  Agents",
            "tools": "🔧  Add Tools",
            "settings": "⚙️  Settings",
        }
        for view, label in nav.items():
            kind = "primary" if st.session_state.view == view else "secondary"
            if st.button(label, key=f"nav_{view}", use_container_width=True, type=kind):
                st.session_state.view = view
                st.rerun()

        st.divider()
        st.markdown("**Projects**")

        projects = st.session_state.projects
        if not projects:
            st.caption("No projects yet. Start a new one.")

        for p in projects:
            active = (
                st.session_state.active_project_id == p.id
                and st.session_state.view == "projects"
            )
            col_open, col_del = st.columns([5, 1])
            if col_open.button(
                f"💬  {p.title}",
                key=f"open_{p.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                state.set_active_project(p.id)
                st.session_state.view = "projects"
                st.rerun()
            if col_del.button("🗑", key=f"delproject_{p.id}", help="Delete project"):
                state.delete_project(p.id)
                st.rerun()


def main() -> None:
    _sidebar()

    view = st.session_state.view
    if view == "agents":
        agent_builder.render()
    elif view == "tools":
        tools.render()
    elif view == "settings":
        settings.render()
    else:
        project.render()


main()
