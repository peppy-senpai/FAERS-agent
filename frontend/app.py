"""FAERS Agent — Streamlit frontend entry point.

Replaces the React App/Layout/Sidebar. Run with:

    streamlit run frontend/app.py
"""

from __future__ import annotations

import streamlit as st

from ui import state
from ui.views import agent_builder, chat, settings, tools

st.set_page_config(page_title="FAERS Agent", page_icon="📊", layout="wide")

state.init_state()


def _sidebar() -> None:
    with st.sidebar:
        # Brand
        st.markdown("### 📊 FAERS Agent")
        st.caption("Safety signal studio")

        # New chat
        if st.button("➕  New Chat", use_container_width=True, type="primary"):
            state.create_chat()
            st.session_state.view = "chat"
            st.rerun()

        # Nav
        nav = {
            "agents": "🤖  Add Agent",
            "tools": "🔧  Add Tools",
            "settings": "⚙️  Settings",
        }
        for view, label in nav.items():
            kind = "primary" if st.session_state.view == view else "secondary"
            if st.button(label, key=f"nav_{view}", use_container_width=True, type=kind):
                st.session_state.view = view
                st.rerun()

        st.divider()
        st.markdown("**Chat history**")

        chats = st.session_state.chats
        if not chats:
            st.caption("No chats yet. Start a new one.")

        for c in chats:
            active = st.session_state.active_chat_id == c.id and st.session_state.view == "chat"
            col_open, col_del = st.columns([5, 1])
            if col_open.button(
                f"💬  {c.title}",
                key=f"open_{c.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                state.set_active_chat(c.id)
                st.session_state.view = "chat"
                st.rerun()
            if col_del.button("🗑", key=f"delchat_{c.id}", help="Delete chat"):
                state.delete_chat(c.id)
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
        chat.render()


main()
