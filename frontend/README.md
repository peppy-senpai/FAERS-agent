# FAERS Agent — Streamlit frontend

A Python (Streamlit) rewrite of the original React/TypeScript frontend. It talks
to the same FastAPI backend over HTTP, so nothing on the backend changes.

## Layout

```
frontend/
├── app.py                  # entry point: sidebar + view router (was App/Layout/Sidebar)
├── requirements.txt
└── faers_ui/
    ├── api.py              # HTTP client for FastAPI    (was services/api.ts)
    ├── state.py            # session state + domain types (was store/appStore.ts)
    └── views/
        ├── chat.py         # chat view        (was components/ChatView.tsx)
        ├── agent_builder.py# agent builder    (was pages/AgentBuilder.tsx)
        ├── tools.py        # tools page       (was pages/ToolsPage.tsx)
        └── settings.py     # settings page    (was pages/SettingsPage.tsx)
```

## Run

```bash
# 1. install deps
pip install -r frontend/requirements.txt

# 2. start the backend (separate terminal, from repo root)
uvicorn backend.main:app --reload --port 8000

# 3. start the frontend
streamlit run frontend/app.py
```

The UI opens at http://localhost:8501.

## Configuration

- `FAERS_API_URL` — backend base URL (default `http://localhost:8000`).

If the backend isn't running, chat falls back to an offline placeholder so the
UI stays usable during development — same behavior as the old React app.
