// Agent Service Client
import { OpenAPI } from "@/client"

export interface AgentQueryRequest {
  query: string
  context_id: string
  agent_type: string
}

export interface AgentQueryResponse {
  response_type: string
  is_task_complete: boolean
  require_user_input: boolean
  content: any
}

export interface AgentStatusResponse {
  agent_name: string
  agent_type: string
  status: string
  description: string
  capabilities: string[]
  is_active: boolean
}

export interface StreamChunk {
  response_type: string
  is_task_complete: boolean
  require_user_input: boolean
  content: any
  error?: string
}

class AgentService {
  private baseURL: string

  constructor() {
    this.baseURL = OpenAPI.BASE || "http://localhost:8000"
  }

  private async makeRequest<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseURL}${endpoint}`
    
    // Get token from localStorage (following the existing auth pattern)
    const token = localStorage.getItem("access_token")
    
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    }

    if (token) {
      headers.Authorization = `Bearer ${token}`
    }

    const response = await fetch(url, {
      ...options,
      headers,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.json()
  }

  // Get status of all agents
  async getAgentsStatus(): Promise<AgentStatusResponse[]> {
    return this.makeRequest<AgentStatusResponse[]>("/api/v1/agents/status")
  }

  // Query an agent (non-streaming)
  async queryAgent(request: AgentQueryRequest): Promise<AgentQueryResponse> {
    return this.makeRequest<AgentQueryResponse>("/api/v1/agents/query", {
      method: "POST",
      body: JSON.stringify(request),
    })
  }

  // Stream agent responses
  async* streamAgentQuery(request: AgentQueryRequest): AsyncGenerator<StreamChunk, void, unknown> {
    const url = `${this.baseURL}/api/v1/agents/query/stream`
    const token = localStorage.getItem("access_token")
    
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    }

    if (token) {
      headers.Authorization = `Bearer ${token}`
    }

    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    if (!response.body) {
      throw new Error("No response body")
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split("\n")

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6))
              yield data as StreamChunk
            } catch (e) {
              console.error("Failed to parse streaming data:", e)
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }

  // Clear agent context
  async clearAgentContext(contextId: string): Promise<{ message: string }> {
    return this.makeRequest<{ message: string }>(`/api/v1/agents/context/${contextId}`, {
      method: "DELETE",
    })
  }
}

export const agentService = new AgentService() 
