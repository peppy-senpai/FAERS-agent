"""Chat view — port of frontend/src/components/ChatView.tsx."""

from __future__ import annotations

import requests
import streamlit as st

from .. import api, state


def _offline_reply(text: str, agent_name: str) -> str:
    """Local placeholder so the UI is usable when the backend is down."""
    return (
        f'(offline) I\'d answer "{text}" using {agent_name}, '
        "but the backend isn't reachable yet."
    )


def render() -> None:
    chat = state.get_chat(st.session_state.active_chat_id)

    if chat is None:
        st.markdown(
            "<div style='text-align:center;padding-top:6rem;color:#888'>"
            "<h3>No chat selected</h3>"
            "<p>Start a new chat from the sidebar to talk to a FAERS agent.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    agent = state.get_agent(chat.agent_id)

    # Header
    st.subheader(chat.title)
    st.caption(f"{agent.name} · {agent.model}" if agent else "No agent")
    st.divider()

    # Messages
    if not chat.messages:
        st.markdown(
            "<div style='text-align:center;padding-top:3rem;color:#888'>"
            "Ask about a drug's adverse-event signals, e.g.<br>"
            "<b>\"What are the top reactions reported for metformin?\"</b>"
            "</div>",
            unsafe_allow_html=True,
        )

    for m in chat.messages:
        avatar = "🧑" if m.role == "user" else "🤖"
        with st.chat_message(m.role, avatar=avatar):
            st.markdown(m.content or "…")

    # Composer
    prompt = st.chat_input("Message the FAERS agent…")
    if not prompt:
        return

    text = prompt.strip()
    if not text:
        return

    state.add_message(chat.id, "user", text)
    with st.chat_message("user", avatar="🧑"):
        st.markdown(text)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                data = api.send_message(text, chat.id)
                reply = data.get("response") or str(data)
            except requests.RequestException:
                reply = _offline_reply(text, agent.name if agent else "the agent")
        st.markdown(reply)

    state.add_message(chat.id, "assistant", reply)
    # Rerun so the sidebar title (first message) and history refresh.
    st.rerun()
