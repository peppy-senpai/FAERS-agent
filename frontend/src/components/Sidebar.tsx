import { NavLink, useNavigate } from "react-router-dom"
import {
  Plus,
  Bot,
  Wrench,
  Settings,
  MessageSquare,
  Trash2,
  Activity,
} from "lucide-react"
import { useAppStore } from "@/store/appStore"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function Sidebar() {
  const navigate = useNavigate()
  const chats = useAppStore((s) => s.chats)
  const activeChatId = useAppStore((s) => s.activeChatId)
  const createChat = useAppStore((s) => s.createChat)
  const setActiveChat = useAppStore((s) => s.setActiveChat)
  const deleteChat = useAppStore((s) => s.deleteChat)

  const handleNewChat = () => {
    const id = createChat()
    navigate(`/chat/${id}`)
  }

  const openChat = (id: string) => {
    setActiveChat(id)
    navigate(`/chat/${id}`)
  }

  const actions = [
    { to: "/agents/new", label: "Add Agent", icon: Bot },
    { to: "/tools", label: "Add Tools", icon: Wrench },
    { to: "/settings", label: "Settings", icon: Settings },
  ]

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      {/* Brand */}
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
          <Activity className="size-4" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold">FAERS Agent</div>
          <div className="text-xs text-muted-foreground">Safety signal studio</div>
        </div>
      </div>

      {/* Create / actions */}
      <div className="space-y-1 px-3">
        <Button className="w-full justify-start" onClick={handleNewChat}>
          <Plus />
          New Chat
        </Button>

        {actions.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60"
              )
            }
          >
            <Icon className="size-4" />
            {label}
          </NavLink>
        ))}
      </div>

      {/* History */}
      <div className="mt-4 px-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Chat history
      </div>
      <nav className="mt-1 flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
        {chats.length === 0 && (
          <p className="px-3 py-2 text-sm text-muted-foreground">
            No chats yet. Start a new one.
          </p>
        )}
        {chats.map((chat) => (
          <div
            key={chat.id}
            className={cn(
              "group flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              activeChatId === chat.id
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "hover:bg-sidebar-accent/60"
            )}
          >
            <button
              className="flex min-w-0 flex-1 items-center gap-2 text-left"
              onClick={() => openChat(chat.id)}
            >
              <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
              <span className="truncate">{chat.title}</span>
            </button>
            <button
              className="opacity-0 transition-opacity group-hover:opacity-100"
              title="Delete chat"
              onClick={(e) => {
                e.stopPropagation()
                deleteChat(chat.id)
              }}
            >
              <Trash2 className="size-4 text-muted-foreground hover:text-destructive" />
            </button>
          </div>
        ))}
      </nav>
    </aside>
  )
}
