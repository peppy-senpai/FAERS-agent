"""HTTP client for the FastAPI backend.

Python port of the original frontend/src/services/api.ts. Each function maps
1:1 to an endpoint the React app used.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Callable, Iterator

import requests


def base_url() -> str:
    """Base URL of the FastAPI backend.

    Overridable with the FAERS_API_URL env var so the same code works in
    dev and deployed setups.
    """
    return os.environ.get("FAERS_API_URL", "http://localhost:8000").rstrip("/")


# ─── Types ────────────────────────────────────────────────


@dataclass
class AgentConfig:
    """What the user configures in the Agent Builder form."""

    agent_name: str
    model: str
    tools: list[str]
    system_prompt: str
    memory_enabled: bool
    human_in_loop: bool


# ─── Agent API calls ──────────────────────────────────────


def create_agent(config: AgentConfig, timeout: float = 10.0) -> dict:
    """Send agent config to FastAPI to build the LangGraph agent."""
    resp = requests.post(
        f"{base_url()}/agent/create",
        json=asdict(config),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def send_message(message: str, thread_id: str, timeout: float = 120.0) -> dict:
    """Send a chat message and get a (non-streamed) response."""
    resp = requests.post(
        f"{base_url()}/agent/chat",
        json={"message": message, "thread_id": thread_id},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# ─── Streaming API call ───────────────────────────────────


def stream_message(
    message: str,
    thread_id: str,
    timeout: float = 120.0,
) -> Iterator[str]:
    """Stream LLM tokens back in real time over SSE.

    Yields each token as it arrives and stops on the "[DONE]" sentinel.
    Mirrors the EventSource logic from the React app, but as a generator so
    it plugs straight into Streamlit's st.write_stream().
    """
    url = f"{base_url()}/agent/stream"
    params = {"message": message, "thread_id": thread_id}
    with requests.get(url, params=params, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            # SSE lines look like "data: <token>"
            line = raw[5:].lstrip() if raw.startswith("data:") else raw
            if line == "[DONE]":
                return
            yield line


# ─── Signal detection API calls ───────────────────────────


def get_signal_data(drug: str, event: str, timeout: float = 30.0) -> dict:
    """Fetch disproportionality analysis results for the dashboard."""
    resp = requests.get(
        f"{base_url()}/signals",
        params={"drug": drug, "event": event},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def health() -> bool:
    """Return True if the backend /health endpoint responds ok."""
    try:
        resp = requests.get(f"{base_url()}/health", timeout=3.0)
        return resp.ok and resp.json().get("status") == "ok"
    except (requests.RequestException, json.JSONDecodeError, ValueError):
        return False
