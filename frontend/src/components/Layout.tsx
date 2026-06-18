import { Outlet } from "react-router-dom"
import { Sidebar } from "@/components/Sidebar"

export function Layout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
