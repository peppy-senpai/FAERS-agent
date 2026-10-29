"""FAERS Agent backend.

FastAPI service that the Streamlit frontend talks to. The
endpoints here are functional scaffolds: they validate the same request/response
shapes the frontend expects so the UI works end-to-end, with placeholder logic
where the real LangGraph agent and FAERS database aren't wired up yet.

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import math
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from . import agent_repo, ingestion, project_repo, tool_repo, working_db
from .tools import AGENT_TOOLS, BUILTIN_TOOL_NAMES, custom_loader, fetch_records
from .python_files.make_python_agent import write_agent_variable


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Load any previously-uploaded custom tools so they survive restarts."""
    try:
        custom_loader.discover_all()
    except Exception as exc:  # noqa: BLE001 - never block startup on a bad tool
        print(f"Custom tool discovery failed: {exc}")
    yield


app = FastAPI(title="FAERS Agent API", version="0.1.0", lifespan=_lifespan)

# Allow the frontend to talk to FastAPI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",  # Streamlit dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ───────────────────────────────────────────────


class AgentConfig(BaseModel):
    """Mirror of the Agent Builder form payload."""

    agent_name: str
    model: str
    tools: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    memory_enabled: bool = True
    human_in_loop: bool = False
    id: str | None = None
    model_source: str = "local"  # local | api
    provider: str = ""  # langchain provider when model_source == "api"
    model_url: str = ""  # base URL when model_source == "api"
    api_key: str = ""  # credential when model_source == "api"
    structured_output: dict | None = None  # {field: description} or None
    knowledge_store: dict = Field(default_factory=dict)

    def to_row(self) -> dict:
        """Map the API payload to ``agent_config`` table columns."""
        return {
            "id": self.id,
            "name": self.agent_name,
            "model": self.model,
            "model_source": self.model_source,
            "provider": self.provider,
            "model_url": self.model_url,
            "api_key": self.api_key,
            "system_prompt": self.system_prompt,
            "structured_output": self.structured_output,
            "tools": self.tools,
            "knowledge_store": self.knowledge_store,
            "memory_enabled": self.memory_enabled,
            "human_in_loop": self.human_in_loop,
        }


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class GraphPayload(BaseModel):
    """A visual graph saved from the node canvas."""

    id: str
    name: str
    graph: dict  # {nodes, edges}
    memory_enabled: bool = True


class ProjectPayload(BaseModel):
    """Mirror of the frontend ``state.Project`` fields we persist."""

    id: str
    title: str = "New project"
    agent_id: str | None = None


# ─── In-memory agent registry ─────────────────────────────
#
# Stand-in for whatever persistence/LangGraph runtime gets wired up later.
# Keyed by agent_name so /agent/create is idempotent per name.
_AGENTS: dict[str, AgentConfig] = {}


# ─── Placeholder reply logic ──────────────────────────────


def _generate_reply(message: str) -> str:
    """Placeholder assistant reply.

    Replace with the real agent invocation once the LangGraph runtime and FAERS
    tools are connected.
    """
    return (
        f'You asked: "{message}". Once the FAERS tools and LLM agent are wired '
        "up, I'll answer with real disproportionality findings (ROR/PRR) and "
        "report counts from the FAERS database."
    )


# ─── Routes ───────────────────────────────────────────────


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "FastAPI is running"}


@app.post("/agent/create")
async def create_agent(config: AgentConfig):
    """Register an agent configuration and persist it to the database.

    Upserts a row in ``agent_config``. Building the actual LangGraph runtime
    from this config is still a placeholder.
    """
    _AGENTS[config.agent_name] = config
    try:
        saved = agent_repo.save_agent(config.to_row())
        agent_variable = write_agent_variable(saved)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Agent file error: {exc}") from exc
    return {"status": "created", "agent": saved, "agent_variable": agent_variable}


@app.post("/agent/graph")
async def create_graph_agent(payload: GraphPayload):
    """Compile a visual graph into LangGraph code, persist it, and register it.

    The graph spec is compiled to a ``build_agent_<id>()`` StateGraph builder,
    written into python_agent.py, and the spec is saved on the agent row. The
    generated builder is executed later (with the LangGraph runtime) to run the
    orchestrated agent.
    """
    from .graph_compiler import compile_graph
    from .python_files.make_python_agent import write_graph_builder

    try:
        code = compile_graph(
            payload.id, payload.graph, memory_enabled=payload.memory_enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        compile(code, "<generated-graph>", "exec")  # catch any codegen bug
    except SyntaxError as exc:  # pragma: no cover - compiler invariant
        raise HTTPException(status_code=500, detail=f"Codegen error: {exc}") from exc

    tool_ids = sorted(
        {
            (n.get("data") or {}).get("tool_id")
            for n in payload.graph.get("nodes", [])
            if n.get("type") == "tool" and (n.get("data") or {}).get("tool_id")
        }
    )
    try:
        write_graph_builder(payload.id, code)
        saved = agent_repo.save_agent(
            {
                "id": payload.id,
                "name": payload.name,
                "model": "",  # graph agents carry per-node models, not one top-level
                "graph": payload.graph,
                "tools": tool_ids,
            }
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Agent file error: {exc}") from exc

    return {"status": "created", "agent": saved, "code": code}


@app.get("/agents")
async def list_agents():
    """Return all agents saved in the database, newest first."""
    try:
        return {"agents": agent_repo.list_agents()}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent by id."""
    try:
        removed = agent_repo.delete_agent(agent_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "id": agent_id}


@app.post("/agent/chat")
async def chat(req: ChatRequest):
    """Send a message and get a single (non-streamed) response."""
    return {
        "thread_id": req.thread_id,
        "response": _generate_reply(req.message),
    }


@app.get("/agent/stream")
async def stream(message: str, thread_id: str):
    """Stream a reply token-by-token as Server-Sent Events.

    Matches the frontend's EventSource / SSE contract: each token arrives as a
    `data:` line, terminated by a `data: [DONE]` sentinel.
    """

    async def event_generator():
        reply = _generate_reply(message)
        for token in reply.split(" "):
            yield f"data: {token} \n\n"
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Tool routes ──────────────────────────────────────────


def _tool_summary(tool, *, builtin: bool) -> dict:
    return {
        "id": tool.name,
        "name": tool.name,
        "description": tool.description or "",
        "builtin": builtin,
    }


@app.get("/tools")
async def list_tools():
    """Return all bindable tools: built-ins plus uploaded custom tools."""
    builtins = [_tool_summary(t, builtin=True) for t in AGENT_TOOLS]
    customs = [_tool_summary(t, builtin=False) for t in custom_loader.custom_tools()]
    return {"tools": builtins + customs}


@app.post("/tools")
async def upload_tool(file: UploadFile = File(...)):
    """Upload a ``.py`` defining LangChain ``@tool`` function(s) and register it.

    The file is validated (must parse and expose at least one tool) before it's
    kept, and tool names may not shadow a built-in. WARNING: importing the file
    executes its code in this process — local, trusted use only.
    """
    filename = Path(file.filename or "tool.py").name
    if not filename.endswith(".py"):
        raise HTTPException(status_code=422, detail="Please upload a .py file.")

    data = await file.read()
    custom_loader._ensure_dir()
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    if safe in custom_loader.RESERVED:
        raise HTTPException(
            status_code=422, detail=f"'{safe}' is a reserved filename."
        )
    tmp = custom_loader.TOOLS_DIR / f".tmp_{uuid.uuid4().hex}.py"
    tmp.write_bytes(data)

    # Validate on the temp copy so a bad upload never overwrites a good file.
    try:
        tools = custom_loader.load_tool_file(tmp)
        clash = {t.name for t in tools} & BUILTIN_TOOL_NAMES
        if clash:
            raise ValueError(
                f"Tool name(s) {sorted(clash)} clash with a built-in tool."
            )
    except ValueError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    final = custom_loader.TOOLS_DIR / safe
    tmp.replace(final)
    try:
        registered = custom_loader.register_file(final)
    except ValueError as exc:  # pragma: no cover - already validated above
        final.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        for t in registered:
            tool_repo.upsert_tool(t.name, t.description or "", final.name)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc

    return {
        "status": "uploaded",
        "tools": [_tool_summary(t, builtin=False) for t in registered],
    }


@app.delete("/tools/{name}")
async def delete_tool(name: str):
    """Delete a custom tool: unregister, remove its file and DB row."""
    if name in BUILTIN_TOOL_NAMES:
        raise HTTPException(status_code=400, detail="Cannot delete a built-in tool.")
    path = custom_loader.path_for(name)
    custom_loader.unregister(name)
    if path:
        Path(path).unlink(missing_ok=True)
    try:
        removed = tool_repo.delete_tool(name)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc
    if not removed and path is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "name": name}


# ─── Project routes ───────────────────────────────────────


@app.post("/projects")
async def create_project(payload: ProjectPayload):
    """Persist a project (upsert by id)."""
    try:
        saved = project_repo.save_project(payload.model_dump())
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc
    return {"status": "saved", "project": saved}


@app.get("/projects")
async def list_projects():
    """Return all persisted projects, newest first."""
    try:
        return {"projects": project_repo.list_projects()}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc


@app.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and drop its working database."""
    try:
        existed = project_repo.delete_project(project_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc
    if not existed:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "id": project_id}


@app.get("/projects/{project_id}/tables")
async def project_tables(project_id: str):
    """List the tables loaded into a project's working database."""
    try:
        return {
            "working_db_name": working_db.working_db_name(project_id),
            "tables": working_db.list_tables(project_id),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc


@app.get("/projects/{project_id}/files")
async def project_files(project_id: str):
    """List the ingest registry (which file became which table)."""
    try:
        return {"files": project_repo.list_project_files(project_id)}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc


@app.get("/projects/{project_id}/tables/{table}/records")
async def project_table_records(
    project_id: str,
    table: str,
    limit: int = 100,
    offset: int = 0,
    order_by: Optional[str] = None,
    descending: bool = False,
):
    """Read a page of rows from a table in the project's working database.

    Paginated so a multi-million-row FAERS table never loads all at once.
    """
    result = fetch_records(
        working_db.working_db_url(project_id),
        table,
        order_by=order_by,
        descending=descending,
        limit=max(1, min(limit, 5000)),
        offset=max(0, offset),
    )
    if not result.ok:
        raise HTTPException(status_code=422, detail=result.error or "read failed")
    return {
        "table": table,
        "rows": result.rows,
        "limit": limit,
        "offset": offset,
    }


@app.post("/projects/{project_id}/files")
async def upload_project_file(
    project_id: str,
    file: UploadFile = File(...),
    table_name: str = Form(""),
    mode: str = Form("replace"),
):
    """Upload a FAERS file and load it into the project's working database.

    Ensures the ``working_db_<id>`` database exists, parses the bytes with
    Polars, and bulk-loads them into a table (named after the file unless a
    ``table_name`` is supplied). Records the outcome in the ingest registry.
    """
    filename = file.filename or "upload"
    target = (table_name.strip() or ingestion.derive_table_name(filename))[:63]
    data = await file.read()

    # Make sure the project exists so the file registry has a valid owner and
    # the working-db name is recorded on the project row.
    try:
        if project_repo.get_project(project_id) is None:
            project_repo.save_project({"id": project_id})
        db_name = working_db.ensure_working_db(project_id)
        project_repo.save_project({"id": project_id, "working_db_name": db_name})
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc

    try:
        df = ingestion.read_any(filename, data)
        rows = ingestion.load_dataframe(df, project_id, target, mode=mode)
    except ValueError as exc:
        # Bad/unsupported input — client error, and record the failure.
        project_repo.add_project_file(
            {
                "id": uuid.uuid4().hex,
                "project_id": project_id,
                "original_filename": filename,
                "table_name": target,
                "file_format": filename.rsplit(".", 1)[-1].lower(),
                "row_count": 0,
                "status": "error",
                "error": str(exc),
            }
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface ingest/load failures cleanly
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}") from exc

    record = project_repo.add_project_file(
        {
            "id": uuid.uuid4().hex,
            "project_id": project_id,
            "original_filename": filename,
            "table_name": target,
            "file_format": filename.rsplit(".", 1)[-1].lower(),
            "row_count": rows,
            "status": "ok",
            "error": None,
        }
    )
    return {"status": "loaded", "file": record}


@app.get("/signals")
async def signals(drug: str, event: str, a: Optional[int] = None):
    """Disproportionality analysis for a drug-event pair.

    Placeholder: returns a deterministic 2x2 contingency table and the derived
    ROR/PRR/chi-square so the dashboard renders. Replace the counts with real
    FAERS queries.
    """
    # 2x2 table:        event   no-event
    #   drug              a         b
    #   other drugs       c         d
    a = a if a is not None else 42
    b, c, d = 120, 360, 50_000

    ror = (a * d) / (b * c) if b and c else float("inf")
    prr = (a / (a + b)) / (c / (c + d)) if (a + b) and (c + d) else float("inf")

    n = a + b + c + d
    expected_a = (a + b) * (a + c) / n
    chi_square = (
        sum(
            (obs - exp) ** 2 / exp
            for obs, exp in [
                (a, expected_a),
                (b, (a + b) * (b + d) / n),
                (c, (c + d) * (a + c) / n),
                (d, (c + d) * (b + d) / n),
            ]
        )
        if n
        else 0.0
    )

    return {
        "drug": drug,
        "event": event,
        "counts": {"a": a, "b": b, "c": c, "d": d},
        "ror": round(ror, 3),
        "prr": round(prr, 3),
        "chi_square": round(chi_square, 3),
        "signal": ror >= 2 and a >= 3 and not math.isinf(ror),
    }
