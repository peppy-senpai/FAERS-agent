"""Tools view — port of frontend/src/pages/ToolsPage.tsx."""

from __future__ import annotations

import streamlit as st

from .. import state


def render() -> None:
    st.subheader("🔧 Tools")
    st.caption("FAERS tools your agents can call. Add custom ones here.")

    # Add tool
    with st.form("add_tool", clear_on_submit=True):
        name = st.text_input("Tool name", placeholder="Tool name")
        description = st.text_area(
            "Description", placeholder="What does this tool do?", height=80
        )
        if st.form_submit_button("➕ Add tool", type="primary"):
            if name.strip():
                state.add_tool(name.strip(), description.strip())
                st.rerun()
            else:
                st.error("Tool name is required.")

    # List
    st.divider()
    for t in st.session_state.tools:
        col_info, col_del = st.columns([6, 1])
        badge = "  `built-in`" if t.builtin else ""
        col_info.markdown(f"**{t.name}**{badge}  \n{t.description}")
        if not t.builtin:
            if col_del.button("🗑", key=f"del_tool_{t.id}", help="Delete tool"):
                state.delete_tool(t.id)
                st.rerun()
