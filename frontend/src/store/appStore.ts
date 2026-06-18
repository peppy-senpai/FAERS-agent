import { create } from "zustand"
import { persist } from "zustand/middleware"

// ─── Domain types ─────────────────────────────────────────

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  createdAt: number
}

export interface Chat {
  id: string
  title: string
  agentId: string | null
  messages: Message[]
  createdAt: number
}

export interface Agent {
  id: string
  name: string
  model: string
  systemPrompt: string
  tools: string[] // tool ids enabled for this agent
  memoryEnabled: boolean
  humanInLoop: boolean
}

export interface Tool {
  id: string
  name: string
  description: string
  builtin?: boolean
}

// ─── Seed data ────────────────────────────────────────────

// FAERS-oriented tools the agents can call. These mirror the backend
// tool layer we'll expose over the local FAERS database.
const BUILTIN_TOOLS: Tool[] = [
  {
    id: "search_adverse_events",
    name: "Search Adverse Events",
    description: "Find adverse event reports for a given drug in FAERS.",
    builtin: true,
  },
  {
    id: "disproportionality",
    name: "Disproportionality (ROR/PRR)",
    description: "Compute ROR, PRR and chi-square for a drug–event pair.",
    builtin: true,
  },
  {
    id: "top_events_for_drug",
    name: "Top Events for Drug",
    description: "List the most frequently reported reactions for a drug.",
    builtin: true,
  },
  {
    id: "report_counts",
    name: "Report Counts",
    description: "Aggregate report counts by age, sex, geography, or quarter.",
    builtin: true,
  },
]

const DEFAULT_AGENT: Agent = {
  id: "default-faers-agent",
  name: "FAERS Safety Analyst",
  model: "claude-opus-4-8",
  systemPrompt:
    "You are a pharmacovigilance analyst. Use the FAERS tools to answer questions about post-marketing drug safety signals. Always cite the counts behind any disproportionality finding.",
  tools: BUILTIN_TOOLS.map((t) => t.id),
  memoryEnabled: true,
  humanInLoop: false,
}

// ─── Store ────────────────────────────────────────────────

interface AppState {
  chats: Chat[]
  agents: Agent[]
  tools: Tool[]
  activeChatId: string | null

  // chat actions
  createChat: (agentId?: string | null) => string
  deleteChat: (id: string) => void
  setActiveChat: (id: string | null) => void
  renameChat: (id: string, title: string) => void
  addMessage: (chatId: string, msg: Omit<Message, "id" | "createdAt">) => string
  appendToMessage: (chatId: string, messageId: string, chunk: string) => void

  // agent actions
  addAgent: (agent: Omit<Agent, "id">) => string
  updateAgent: (id: string, patch: Partial<Agent>) => void
  deleteAgent: (id: string) => void

  // tool actions
  addTool: (tool: Omit<Tool, "id">) => string
  deleteTool: (id: string) => void
}

const uid = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2)

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      chats: [],
      agents: [DEFAULT_AGENT],
      tools: BUILTIN_TOOLS,
      activeChatId: null,

      createChat: (agentId) => {
        const id = uid()
        const chat: Chat = {
          id,
          title: "New chat",
          agentId: agentId ?? get().agents[0]?.id ?? null,
          messages: [],
          createdAt: Date.now(),
        }
        set((s) => ({ chats: [chat, ...s.chats], activeChatId: id }))
        return id
      },

      deleteChat: (id) =>
        set((s) => {
          const chats = s.chats.filter((c) => c.id !== id)
          return {
            chats,
            activeChatId:
              s.activeChatId === id ? chats[0]?.id ?? null : s.activeChatId,
          }
        }),

      setActiveChat: (id) => set({ activeChatId: id }),

      renameChat: (id, title) =>
        set((s) => ({
          chats: s.chats.map((c) => (c.id === id ? { ...c, title } : c)),
        })),

      addMessage: (chatId, msg) => {
        const id = uid()
        set((s) => ({
          chats: s.chats.map((c) =>
            c.id === chatId
              ? {
                  ...c,
                  // first user message becomes the chat title
                  title:
                    c.messages.length === 0 && msg.role === "user"
                      ? msg.content.slice(0, 40)
                      : c.title,
                  messages: [
                    ...c.messages,
                    { ...msg, id, createdAt: Date.now() },
                  ],
                }
              : c
          ),
        }))
        return id
      },

      appendToMessage: (chatId, messageId, chunk) =>
        set((s) => ({
          chats: s.chats.map((c) =>
            c.id === chatId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === messageId
                      ? { ...m, content: m.content + chunk }
                      : m
                  ),
                }
              : c
          ),
        })),

      addAgent: (agent) => {
        const id = uid()
        set((s) => ({ agents: [...s.agents, { ...agent, id }] }))
        return id
      },

      updateAgent: (id, patch) =>
        set((s) => ({
          agents: s.agents.map((a) => (a.id === id ? { ...a, ...patch } : a)),
        })),

      deleteAgent: (id) =>
        set((s) => ({ agents: s.agents.filter((a) => a.id !== id) })),

      addTool: (tool) => {
        const id = uid()
        set((s) => ({ tools: [...s.tools, { ...tool, id }] }))
        return id
      },

      deleteTool: (id) =>
        set((s) => ({ tools: s.tools.filter((t) => t.id !== id) })),
    }),
    { name: "faers-agent-store" }
  )
)
