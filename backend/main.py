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
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from . import agent_repo

app = FastAPI(title="FAERS Agent API", version="0.1.0")

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
            "tools": self.tools,
            "knowledge_store": self.knowledge_store,
            "memory_enabled": self.memory_enabled,
            "human_in_loop": self.human_in_loop,
        }


class ChatRequest(BaseModel):
    message: str
    thread_id: str


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
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}") from exc
    return {"status": "created", "agent": saved}


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
