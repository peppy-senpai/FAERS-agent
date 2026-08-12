"""Project view — port of frontend/src/components/ChatView.tsx."""

from __future__ import annotations

import math
import re

import requests
import streamlit as st

from .. import api, state


def _offline_reply(text: str, agent_name: str) -> str:
    """Local placeholder so the UI is usable when the backend is down."""
    return (
        f'(offline) I\'d answer "{text}" using {agent_name}, '
        "but the backend isn't reachable yet."
    )


def _derive_table_name(filename: str) -> str:
    """Client-side preview of the table name (backend derives the same way)."""
    stem = filename.rsplit(".", 1)[0].lower() if "." in filename else filename.lower()
    stem = re.sub(r"[_\- ]*\d{2,4}q[1-4]$", "", stem)
    stem = re.sub(r"[_\- ]*\d{4,8}$", "", stem)
    name = re.sub(r"[^a-z0-9_]", "_", stem).strip("_")
    return (name or "table")[:63]


def _http_error_detail(exc: requests.HTTPError) -> str:
    """Pull the FastAPI ``detail`` message out of an error response."""
    try:
        return exc.response.json().get("detail", str(exc))
    except (ValueError, AttributeError):
        return str(exc)


def _data_section(project: state.Project) -> None:
    """Upload FAERS files into the project's working database and list tables."""
    with st.expander("📁 Project data — upload FAERS files", expanded=False):
        try:
            info = api.list_project_tables(project.id)
        except requests.HTTPError as exc:
            # Backend is up but returned an error (e.g. DB unreachable) — show why.
            st.warning(f"Data upload unavailable: {_http_error_detail(exc)}")
            return
        except requests.RequestException:
            st.caption("Backend unreachable — start the FastAPI server on :8000.")
            return

        db_name = info.get("working_db_name", "")
        tables = info.get("tables", [])
        if tables:
            st.caption(f"Database `{db_name}` · {len(tables)} table(s)")
            st.table(
                {
                    "table": [t["table"] for t in tables],
                    "rows": [t["row_count"] for t in tables],
                }
            )
        else:
            st.caption(f"No data yet. Uploads create `{db_name}`.")

        uploads = st.file_uploader(
            "Upload FAERS files (demo, drug, indi, reac, …)",
            accept_multiple_files=True,
            type=["csv", "txt", "tsv", "dat", "xlsx", "xls", "json", "ndjson", "parquet"],
            key=f"data_upload_{project.id}",
        )
        for f in uploads or []:
            st.divider()
            st.write(f"**{f.name}**")
            col_name, col_mode = st.columns([3, 2])
            table_name = col_name.text_input(
                "Table name",
                value=_derive_table_name(f.name),
                key=f"tbl_{project.id}_{f.name}",
            )
            mode = col_mode.radio(
                "If the table exists",
                ["replace", "append"],
                horizontal=True,
                key=f"mode_{project.id}_{f.name}",
            )
            if st.button(
                f"Load into `{table_name}`", key=f"load_{project.id}_{f.name}"
            ):
                with st.spinner(f"Loading {f.name}…"):
                    try:
                        res = api.upload_file(
                            project.id,
                            f.name,
                            f.getvalue(),
                            table_name=table_name,
                            mode=mode,
                        )
                    except requests.HTTPError as exc:
                        st.error(f"Upload failed: {_http_error_detail(exc)}")
                        continue
                    except requests.RequestException as exc:
                        st.error(f"Upload failed: {exc}")
                        continue
                rows = res.get("file", {}).get("row_count", 0)
                st.success(f"Loaded {rows} row(s) into `{table_name}`.")
                st.rerun()


def _records_viewer(project: state.Project) -> None:
    """Browse the rows of a project's uploaded tables, paginated."""
    st.markdown("#### Browse records")
    try:
        info = api.list_project_tables(project.id)
    except requests.HTTPError as exc:
        st.warning(f"Records unavailable: {_http_error_detail(exc)}")
        return
    except requests.RequestException:
        st.caption("Backend unreachable — start the FastAPI server on :8000.")
        return

    counts = {t["table"]: t["row_count"] for t in info.get("tables", [])}
    if not counts:
        st.caption("No tables yet. Upload a file above to browse its records here.")
        return

    col_tbl, col_size = st.columns([2, 1])
    table = col_tbl.selectbox("Table", list(counts), key=f"rec_tbl_{project.id}")
    page_size = col_size.selectbox(
        "Rows per page", [50, 100, 500, 1000], key=f"rec_ps_{project.id}"
    )
    total = counts.get(table, 0)
    pages = max(1, math.ceil(total / page_size))

    # Current page is tracked per (project, table) so each table remembers its
    # position. The nav buttons mutate it in place; no explicit rerun needed
    # since a button click already reruns the script top-to-bottom.
    page_key = f"rec_page_{project.id}_{table}"
    page = st.session_state.get(page_key, 1)

    c_first, c_prev, c_label, c_next, c_last = st.columns([1, 1, 3, 1, 1])
    if c_first.button("⏮", key=f"first_{page_key}", disabled=page <= 1, help="First"):
        page = 1
    if c_prev.button("◀", key=f"prev_{page_key}", disabled=page <= 1, help="Previous"):
        page -= 1
    if c_next.button("▶", key=f"next_{page_key}", disabled=page >= pages, help="Next"):
        page += 1
    if c_last.button("⏭", key=f"last_{page_key}", disabled=page >= pages, help="Last"):
        page = pages
    page = min(max(1, page), pages)
    st.session_state[page_key] = page
    c_label.markdown(
        f"<div style='text-align:center;padding-top:0.45rem;color:#666'>"
        f"Page <b>{page}</b> of {pages}</div>",
        unsafe_allow_html=True,
    )

    offset = (page - 1) * page_size
    try:
        data = api.get_project_records(
            project.id, table, limit=page_size, offset=offset
        )
    except requests.HTTPError as exc:
        st.error(f"Read failed: {_http_error_detail(exc)}")
        return
    except requests.RequestException as exc:
        st.error(f"Read failed: {exc}")
        return

    rows = data.get("rows", [])
    first = offset + 1 if rows else 0
    st.caption(f"Showing rows {first:,}–{offset + len(rows):,} of {total:,}")
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _chat_tab(project: state.Project, agent) -> None:
    """The conversation surface: history + composer."""
    if not project.messages:
        st.markdown(
            "<div style='text-align:center;padding-top:3rem;color:#888'>"
            "Ask about a drug's adverse-event signals, e.g.<br>"
            "<b>\"What are the top reactions reported for metformin?\"</b>"
            "</div>",
            unsafe_allow_html=True,
        )

    for m in project.messages:
        avatar = "🧑" if m.role == "user" else "🤖"
        with st.chat_message(m.role, avatar=avatar):
            st.markdown(m.content or "…")

    prompt = st.chat_input("Message the FAERS agent…")
    if not prompt:
        return
    text = prompt.strip()
    if not text:
        return

    state.add_message(project.id, "user", text)
    with st.chat_message("user", avatar="🧑"):
        st.markdown(text)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                data = api.send_message(text, project.id)
                reply = data.get("response") or str(data)
            except requests.RequestException:
                reply = _offline_reply(text, agent.name if agent else "the agent")
        st.markdown(reply)

    state.add_message(project.id, "assistant", reply)
    # Rerun so the sidebar title (first message) and history refresh.
    st.rerun()


def render() -> None:
    project = state.get_project(st.session_state.active_project_id)

    if project is None:
        st.markdown(
            "<div style='text-align:center;padding-top:6rem;color:#888'>"
            "<h3>No project selected</h3>"
            "<p>Start a new project from the sidebar to talk to a FAERS agent.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    agent = state.get_agent(project.agent_id)

    # Header
    st.subheader(project.title)
    st.caption(f"{agent.name} · {agent.model}" if agent else "No agent")

    tab_chat, tab_records = st.tabs(["💬 Chat", "📊 Records"])
    with tab_chat:
        _chat_tab(project, agent)
    with tab_records:
        _data_section(project)
        st.divider()
        _records_viewer(project)
