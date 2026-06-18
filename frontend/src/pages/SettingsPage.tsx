import { useEffect, useState } from "react"
import { Settings as SettingsIcon, Sun, Moon } from "lucide-react"
import { Button } from "@/components/ui/button"

type Theme = "light" | "dark"

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark")
  localStorage.setItem("faers-theme", theme)
}

export function SettingsPage() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("faers-theme") as Theme) || "light"
  )

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <SettingsIcon className="size-5" />
        </div>
        <div>
          <h1 className="text-lg font-semibold">Settings</h1>
          <p className="text-sm text-muted-foreground">
            Appearance and backend configuration.
          </p>
        </div>
      </div>

      <div className="space-y-6">
        <section className="space-y-2">
          <h2 className="text-sm font-medium">Theme</h2>
          <div className="flex gap-2">
            <Button
              variant={theme === "light" ? "default" : "outline"}
              onClick={() => setTheme("light")}
            >
              <Sun />
              Light
            </Button>
            <Button
              variant={theme === "dark" ? "default" : "outline"}
              onClick={() => setTheme("dark")}
            >
              <Moon />
              Dark
            </Button>
          </div>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-medium">Backend</h2>
          <div className="rounded-md border border-border px-4 py-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">API base URL</span>
              <code className="text-xs">http://localhost:8000</code>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            The FastAPI backend powers chat and FAERS tool calls. Chats fall back
            to an offline placeholder when it isn't reachable.
          </p>
        </section>
      </div>
    </div>
  )
}
