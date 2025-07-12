import { createFileRoute, redirect } from "@tanstack/react-router"
import React from "react"

import LandingPage from "@/components/LandingPage/LandingPage"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/")({
  component: HomePage,
  beforeLoad: async () => {
    if (isLoggedIn()) {
      throw redirect({
        to: "/code-search",
      })
    }
  },
})

function HomePage() {
  return <LandingPage />
}

export default HomePage 
