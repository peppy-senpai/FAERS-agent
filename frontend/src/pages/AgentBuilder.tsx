import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Bot, Trash2 } from "lucide-react"
import { useAppStore } from "@/store/appStore"
import { Button } from "@/components/ui/button"
import { createAgent } from "@/services/api"

const MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]

export function AgentBuilder() {
  const navigate = useNavigate()
  const tools = useAppStore((s) => s.tools)
  const agents = useAppStore((s) => s.agents)
  const addAgent = useAppStore((s) => s.addAgent)
  const deleteAgent = useAppStore((s) => s.deleteAgent)

  const [name, setName] = useState("")
  const [model, setModel] = useState(MODELS[0])
  const [systemPrompt, setSystemPrompt] = useState("")
  const [selectedTools, setSelectedTools] = useState<string[]>([])
  const [memoryEnabled, setMemoryEnabled] = useState(true)
  const [humanInLoop, setHumanInLoop] = useState(false)

  const toggleTool = (id: string) =>
    setSelectedTools((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]
    )

  const handleCreate = async () => {
    if (!name.trim()) return
    addAgent({
      name: name.trim(),
      model,
      systemPrompt,
      tools: selectedTools,
      memoryEnabled,
      humanInLoop,
    })
    // Best-effort: tell the backend to build the runtime agent too.
    try {
      await createAgent({
        agent_name: name.trim(),
        model,
        tools: selectedTools,
        system_prompt: systemPrompt,
        memory_enabled: memoryEnabled,
        human_in_loop: humanInLoop,
      })
    } catch {
      // backend optional during development
    }
    navigate("/")
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Bot className="size-5" />
        </div>
        <div>
          <h1 className="text-lg font-semibold">Add Agent</h1>
          <p className="text-sm text-muted-foreground">
            Configure an agent and the FAERS tools it can use.
          </p>
        </div>
      </div>

      <div className="space-y-5">
        <Field label="Agent name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="FAERS Safety Analyst"
            className={inputCls}
          />
        </Field>

        <Field label="Model">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className={inputCls}
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Field>

        <Field label="System prompt">
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={4}
            placeholder="You are a pharmacovigilance analyst…"
            className={`${inputCls} resize-y`}
          />
        </Field>

        <Field label="Tools">
          <div className="space-y-2">
            {tools.map((t) => (
              <label
                key={t.id}
                className="flex cursor-pointer items-start gap-3 rounded-md border border-border p-3 hover:bg-accent/40"
              >
                <input
                  type="checkbox"
                  checked={selectedTools.includes(t.id)}
                  onChange={() => toggleTool(t.id)}
                  className="mt-1"
                />
                <div>
                  <div className="text-sm font-medium">{t.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {t.description}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </Field>

        <div className="flex gap-6">
          <Toggle label="Memory" checked={memoryEnabled} onChange={setMemoryEnabled} />
          <Toggle
            label="Human in the loop"
            checked={humanInLoop}
            onChange={setHumanInLoop}
          />
        </div>

        <div className="flex gap-2 pt-2">
          <Button onClick={handleCreate} disabled={!name.trim()}>
            Create agent
          </Button>
          <Button variant="ghost" onClick={() => navigate("/")}>
            Cancel
          </Button>
        </div>
      </div>

      {/* Existing agents */}
      <div className="mt-10">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Your agents
        </h2>
        <div className="space-y-2">
          {agents.map((a) => (
            <div
              key={a.id}
              className="flex items-center justify-between rounded-md border border-border px-4 py-3"
            >
              <div>
                <div className="text-sm font-medium">{a.name}</div>
                <div className="text-xs text-muted-foreground">
                  {a.model} · {a.tools.length} tools
                </div>
              </div>
              <button
                onClick={() => deleteAgent(a.id)}
                title="Delete agent"
                disabled={agents.length === 1}
                className="text-muted-foreground hover:text-destructive disabled:opacity-30"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const inputCls =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {children}
    </div>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}
