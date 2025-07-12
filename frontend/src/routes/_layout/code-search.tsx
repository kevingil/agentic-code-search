import { createFileRoute } from "@tanstack/react-router"
import React from "react"

import CodeSearch from "@/components/CodeSearch/CodeSearch"

export const Route = createFileRoute("/_layout/code-search")({
  component: CodeSearchPage,
})

function CodeSearchPage() {
  return <CodeSearch />
}

export default CodeSearchPage 
