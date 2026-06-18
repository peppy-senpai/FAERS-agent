import { useEffect } from "react"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Layout } from "@/components/Layout"
import { ChatView } from "@/components/ChatView"
import { AgentBuilder } from "@/pages/AgentBuilder"
import { ToolsPage } from "@/pages/ToolsPage"
import { SettingsPage } from "@/pages/SettingsPage"

function App() {
  // Restore the saved theme on load.
  useEffect(() => {
    const theme = localStorage.getItem("faers-theme")
    document.documentElement.classList.toggle("dark", theme === "dark")
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<ChatView />} />
          <Route path="chat/:chatId" element={<ChatView />} />
          <Route path="agents/new" element={<AgentBuilder />} />
          <Route path="tools" element={<ToolsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
