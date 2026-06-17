// Base URL of your FastAPI backend
const BASE_URL = "http://localhost:8000"

// ─── Types ────────────────────────────────────────────────

// What the user configures in the Agent Builder form
export interface AgentConfig {
  agent_name: string
  model: string
  tools: string[]
  system_prompt: string
  memory_enabled: boolean
  human_in_loop: boolean
}

// A single chat message
export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

// ─── Agent API Calls ──────────────────────────────────────

// Send agent config to FastAPI to build the LangGraph agent
export const createAgent = async (config: AgentConfig) => {
  const response = await fetch(`${BASE_URL}/agent/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  })

  if (!response.ok) {
    throw new Error("Failed to create agent")
  }

  return response.json()
}

// Send a chat message and get a response
export const sendMessage = async (message: string, thread_id: string) => {
  const response = await fetch(`${BASE_URL}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id }),
  })

  if (!response.ok) {
    throw new Error("Failed to send message")
  }

  return response.json()
}

// ─── Streaming API Call ───────────────────────────────────

// Stream LLM tokens back in real time using SSE
export const streamMessage = (
  message: string,
  thread_id: string,
  onToken: (token: string) => void,  // called for each token
  onDone: () => void                  // called when stream ends
) => {
  // SSE is a browser built-in — no library needed
  const url = `${BASE_URL}/agent/stream?message=${encodeURIComponent(message)}&thread_id=${thread_id}`
  const eventSource = new EventSource(url)

  // Each token arrives as an event
  eventSource.onmessage = (event) => {
    if (event.data === "[DONE]") {
      eventSource.close()
      onDone()
    } else {
      onToken(event.data)
    }
  }

  eventSource.onerror = () => {
    eventSource.close()
    onDone()
  }

  // Return eventSource so caller can close it if needed
  return eventSource
}

// ─── Signal Detection API Calls ───────────────────────────

// Fetch disproportionality analysis results for dashboard
export const getSignalData = async (drug: string, event: string) => {
  const response = await fetch(
    `${BASE_URL}/signals?drug=${drug}&event=${event}`
  )

  if (!response.ok) {
    throw new Error("Failed to fetch signal data")
  }

  return response.json()
}