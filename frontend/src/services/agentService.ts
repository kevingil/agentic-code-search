// Agent Service Client
import { OpenAPI } from "@/client"

export interface AgentQueryRequest {
  query: string
  context_id: string
  agent_type: string
  github_url?: string
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

export interface CodeSearchSession {
  id: string
  name: string
  github_url?: string
  agent_type: string
  created_at: Date
  last_used: Date
  messages: Array<{
    id: string
    type: "user" | "agent"
    content: string
    timestamp: Date
    status: "sending" | "streaming" | "complete" | "error"
    metadata?: any
  }>
}

export interface SessionsStorageData {
  sessions: CodeSearchSession[]
  activeSessionId: string | null
}

class AgentService {
  private baseURL: string
  private storageKey = "codeSearch_sessions"

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

  // Session Management Methods
  private getSessionsData(): SessionsStorageData {
    const data = localStorage.getItem(this.storageKey)
    return data ? JSON.parse(data) : { sessions: [], activeSessionId: null }
  }

  private saveSessionsData(data: SessionsStorageData): void {
    localStorage.setItem(this.storageKey, JSON.stringify(data))
  }

  getSessions(): CodeSearchSession[] {
    const data = this.getSessionsData()
    return data.sessions.map(session => ({
      ...session,
      created_at: new Date(session.created_at),
      last_used: new Date(session.last_used),
      messages: session.messages.map(msg => ({
        ...msg,
        timestamp: new Date(msg.timestamp)
      }))
    }))
  }

  createSession(name: string, agentType: string = "orchestrator", githubUrl?: string): CodeSearchSession {
    const session: CodeSearchSession = {
      id: `session_${Date.now()}`,
      name,
      github_url: githubUrl,
      agent_type: agentType,
      created_at: new Date(),
      last_used: new Date(),
      messages: []
    }

    const data = this.getSessionsData()
    data.sessions.unshift(session)
    data.activeSessionId = session.id
    this.saveSessionsData(data)

    return session
  }

  getSession(sessionId: string): CodeSearchSession | null {
    const sessions = this.getSessions()
    return sessions.find(s => s.id === sessionId) || null
  }

  updateSession(sessionId: string, updates: Partial<CodeSearchSession>): void {
    const data = this.getSessionsData()
    const sessionIndex = data.sessions.findIndex(s => s.id === sessionId)
    
    if (sessionIndex !== -1) {
      data.sessions[sessionIndex] = {
        ...data.sessions[sessionIndex],
        ...updates,
        last_used: new Date()
      }
      this.saveSessionsData(data)
    }
  }

  deleteSession(sessionId: string): void {
    const data = this.getSessionsData()
    data.sessions = data.sessions.filter(s => s.id !== sessionId)
    
    if (data.activeSessionId === sessionId) {
      data.activeSessionId = data.sessions.length > 0 ? data.sessions[0].id : null
    }
    
    this.saveSessionsData(data)
  }

  setActiveSession(sessionId: string): void {
    const data = this.getSessionsData()
    data.activeSessionId = sessionId
    this.saveSessionsData(data)
  }

  clearActiveSession(): void {
    const data = this.getSessionsData()
    data.activeSessionId = null
    this.saveSessionsData(data)
  }

  getActiveSession(): CodeSearchSession | null {
    const data = this.getSessionsData()
    return data.activeSessionId ? this.getSession(data.activeSessionId) : null
  }

  addMessageToSession(sessionId: string, message: CodeSearchSession['messages'][0]): void {
    const data = this.getSessionsData()
    const sessionIndex = data.sessions.findIndex(s => s.id === sessionId)
    
    if (sessionIndex !== -1) {
      data.sessions[sessionIndex].messages.push(message)
      data.sessions[sessionIndex].last_used = new Date()
      this.saveSessionsData(data)
    }
  }

  updateMessageInSession(sessionId: string, messageId: string, updates: Partial<CodeSearchSession['messages'][0]>): void {
    const data = this.getSessionsData()
    const sessionIndex = data.sessions.findIndex(s => s.id === sessionId)
    
    if (sessionIndex !== -1) {
      const messageIndex = data.sessions[sessionIndex].messages.findIndex(m => m.id === messageId)
      if (messageIndex !== -1) {
        data.sessions[sessionIndex].messages[messageIndex] = {
          ...data.sessions[sessionIndex].messages[messageIndex],
          ...updates
        }
        this.saveSessionsData(data)
      }
    }
  }
}

export const agentService = new AgentService() 
