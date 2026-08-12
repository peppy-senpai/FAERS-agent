"""Tools view — upload custom Python tools and manage the tool registry."""

from __future__ import annotations

import requests
import streamlit as st

from .. import api, state

_TEMPLATE = '''from langchain_core.tools import tool


@tool
def word_count(text: str) -> int:
    """Return the number of words in the given text."""
    return len(text.split())
'''


def _http_error_detail(exc: requests.HTTPError) -> str:
    try:
        return exc.response.json().get("detail", str(exc))
    except (ValueError, AttributeError):
        return str(exc)


def render() -> None:
    st.subheader("🔧 Tools")
    st.caption("Tools your agents can call. Upload custom ones as Python files.")

    # ─── Upload a custom tool ─────────────────────────────
    st.markdown("#### Upload a tool")
    st.caption(
        "The file must define one or more functions decorated with LangChain's "
        "`@tool`. ⚠️ Uploaded code runs on the server — only upload code you trust."
    )
    with st.expander("Example tool file"):
        st.code(_TEMPLATE, language="python")

    upload = st.file_uploader("Python tool file", type=["py"], key="tool_upload")
    if upload is not None and st.button("➕ Upload tool", type="primary"):
        with st.spinner(f"Validating {upload.name}…"):
            try:
                res = api.upload_tool(upload.name, upload.getvalue())
            except requests.HTTPError as exc:
                st.error(f"Upload rejected: {_http_error_detail(exc)}")
                res = None
            except requests.RequestException as exc:
                st.error(f"Upload failed: {exc}")
                res = None
        if res is not None:
            names = ", ".join(t["name"] for t in res.get("tools", []))
            st.success(f"Registered tool(s): {names}")
            state.refresh_tools()
            st.rerun()

    # ─── Registered tools ─────────────────────────────────
    st.divider()
    st.markdown("#### Registered tools")
    for t in st.session_state.tools:
        col_info, col_del = st.columns([6, 1])
        badge = "  `built-in`" if t.builtin else "  `custom`"
        col_info.markdown(f"**{t.name}**{badge}  \n{t.description}")
        if not t.builtin:
            if col_del.button("🗑", key=f"del_tool_{t.id}", help="Delete tool"):
                state.delete_tool(t.id)
                st.rerun()
