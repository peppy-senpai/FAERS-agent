"""Settings view — port of frontend/src/pages/SettingsPage.tsx."""

from __future__ import annotations

import streamlit as st

from .. import api


def render() -> None:
    st.subheader("⚙️ Settings")
    st.caption("Appearance and backend configuration.")

    # Theme
    st.markdown("##### Theme")
    st.radio(
        "Theme",
        ["light", "dark"],
        index=0 if st.session_state.theme == "light" else 1,
        horizontal=True,
        label_visibility="collapsed",
        key="theme",
    )
    st.caption(
        "Streamlit's actual light/dark palette is set in .streamlit/config.toml "
        "or the ⋮ menu → Settings. This preference is stored for the session."
    )

    # Backend
    st.divider()
    st.markdown("##### Backend")
    reachable = api.health()
    status = "🟢 reachable" if reachable else "🔴 not reachable"
    st.markdown(
        f"- **API base URL:** `{api.base_url()}`\n"
        f"- **Status:** {status}"
    )
    st.caption(
        "The FastAPI backend powers chat and FAERS tool calls. Projects fall back "
        "to an offline placeholder when it isn't reachable. Override the URL with "
        "the FAERS_API_URL environment variable."
    )
