import { useState } from "react"
import { Wrench, Trash2, Plus } from "lucide-react"
import { useAppStore } from "@/store/appStore"
import { Button } from "@/components/ui/button"

const inputCls =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

export function ToolsPage() {
  const tools = useAppStore((s) => s.tools)
  const addTool = useAppStore((s) => s.addTool)
  const deleteTool = useAppStore((s) => s.deleteTool)

  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  const handleAdd = () => {
    if (!name.trim()) return
    addTool({ name: name.trim(), description: description.trim() })
    setName("")
    setDescription("")
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Wrench className="size-5" />
        </div>
        <div>
          <h1 className="text-lg font-semibold">Tools</h1>
          <p className="text-sm text-muted-foreground">
            FAERS tools your agents can call. Add custom ones here.
          </p>
        </div>
      </div>

      {/* Add tool */}
      <div className="space-y-3 rounded-md border border-border p-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tool name"
          className={inputCls}
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="What does this tool do?"
          className={`${inputCls} resize-y`}
        />
        <Button onClick={handleAdd} disabled={!name.trim()}>
          <Plus />
          Add tool
        </Button>
      </div>

      {/* List */}
      <div className="mt-8 space-y-2">
        {tools.map((t) => (
          <div
            key={t.id}
            className="flex items-start justify-between gap-3 rounded-md border border-border px-4 py-3"
          >
            <div>
              <div className="flex items-center gap-2 text-sm font-medium">
                {t.name}
                {t.builtin && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    built-in
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground">{t.description}</div>
            </div>
            {!t.builtin && (
              <button
                onClick={() => deleteTool(t.id)}
                title="Delete tool"
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="size-4" />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
