import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router-dom"
import { Send, Bot, User } from "lucide-react"
import { useAppStore } from "@/store/appStore"
import { Button } from "@/components/ui/button"
import { sendMessage } from "@/services/api"

export function ChatView() {
  const { chatId } = useParams()
  const chats = useAppStore((s) => s.chats)
  const agents = useAppStore((s) => s.agents)
  const addMessage = useAppStore((s) => s.addMessage)
  const appendToMessage = useAppStore((s) => s.appendToMessage)
  const setActiveChat = useAppStore((s) => s.setActiveChat)

  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const chat = chats.find((c) => c.id === chatId) ?? null
  const agent = agents.find((a) => a.id === chat?.agentId) ?? agents[0]

  useEffect(() => {
    if (chatId) setActiveChat(chatId)
  }, [chatId, setActiveChat])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [chat?.messages.length, busy])

  if (!chat) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <Bot className="size-10 text-muted-foreground" />
        <h2 className="text-lg font-medium">No chat selected</h2>
        <p className="text-sm text-muted-foreground">
          Start a new chat from the sidebar to talk to a FAERS agent.
        </p>
      </div>
    )
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || busy) return
    setInput("")
    setBusy(true)

    addMessage(chat.id, { role: "user", content: text })
    const assistantId = addMessage(chat.id, { role: "assistant", content: "" })

    try {
      const data = await sendMessage(text, chat.id)
      appendToMessage(chat.id, assistantId, data.response ?? JSON.stringify(data))
    } catch {
      // Backend not running yet — fall back to a local placeholder so the
      // UI is usable standalone during development.
      appendToMessage(
        chat.id,
        assistantId,
        `(offline) I'd answer "${text}" using ${agent?.name ?? "the agent"}, ` +
          `but the backend isn't reachable yet.`
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-6 py-3">
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold">{chat.title}</h1>
          <p className="text-xs text-muted-foreground">
            {agent ? `${agent.name} · ${agent.model}` : "No agent"}
          </p>
        </div>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
        {chat.messages.length === 0 && (
          <div className="mx-auto max-w-md pt-16 text-center text-muted-foreground">
            <Bot className="mx-auto mb-3 size-8" />
            <p className="text-sm">
              Ask about a drug's adverse-event signals, e.g.
              <br />
              <span className="text-foreground">
                "What are the top reactions reported for metformin?"
              </span>
            </p>
          </div>
        )}

        {chat.messages.map((m) => (
          <div key={m.id} className="flex gap-3">
            <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted">
              {m.role === "user" ? (
                <User className="size-4" />
              ) : (
                <Bot className="size-4" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-muted-foreground">
                {m.role === "user" ? "You" : agent?.name ?? "Assistant"}
              </div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {m.content || (busy ? "…" : "")}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Composer */}
      <div className="border-t border-border p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            rows={1}
            placeholder="Message the FAERS agent…"
            className="max-h-40 min-h-[2.5rem] flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button size="icon" onClick={handleSend} disabled={busy || !input.trim()}>
            <Send />
          </Button>
        </div>
      </div>
    </div>
  )
}
