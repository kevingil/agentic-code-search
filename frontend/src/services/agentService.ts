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

export interface Message {
  id: string
  type: "user" | "agent"
  content: string
  timestamp: Date
  status: "sending" | "streaming" | "complete" | "error"
  metadata?: any
}

export interface CodeSearchSession {
  id: string
  name: string
  github_url?: string
  agent_type: string
  created_at: Date
  last_used: Date
  is_active: boolean
  vector_embeddings_processed: boolean
  updated_at: Date
  owner_id: string
  
}

export interface CodeSearchSessionCreate {
  name: string
  github_url?: string
  agent_type?: string
}

export interface CodeSearchSessionsResponse {
  data: CodeSearchSession[]
  count: number
}

export interface EmbeddingsStatus {
  session_id: string
  embeddings_processed: boolean
  embeddings_count: number
  created_at: Date
  updated_at: Date
}

class AgentService {
  private baseURL: string
  private activeSessionId: string | null = null
  private sessionsCache: CodeSearchSession[] = []
  private messagesCache: Map<string, Message[]> = new Map() // sessionId -> messages

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

  // Stream agent query responses
  async* streamAgentQuery(request: AgentQueryRequest): AsyncGenerator<StreamChunk, void, unknown> {
    const url = `${this.baseURL}/api/v1/agents/query/stream`
    
    const token = localStorage.getItem("access_token")
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
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

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()

    if (!reader) {
      throw new Error("No response body")
    }

    let buffer = ""

    try {
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          break
        }

        buffer += decoder.decode(value, { stream: true })
        
        // Process complete lines
        const lines = buffer.split('\n')
        buffer = lines.pop() || "" // Keep incomplete line in buffer
        
        for (const line of lines) {
          if (line.trim() === "") continue
          
          // Parse SSE format
          if (line.startsWith("data: ")) {
            const data = line.slice(6)
            try {
              const chunk = JSON.parse(data)
              yield chunk
            } catch (e) {
              console.error("Failed to parse chunk:", e)
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

  // Session Management Methods using backend API
  async getSessions(): Promise<CodeSearchSession[]> {
    try {
      const response = await this.makeRequest<CodeSearchSessionsResponse>("/api/v1/code-search/sessions")
      this.sessionsCache = response.data.map(session => ({
        ...session,
        created_at: new Date(session.created_at),
        last_used: new Date(session.last_used),
        updated_at: new Date(session.updated_at)
      }))
      return this.sessionsCache
    } catch (error) {
      console.error("Failed to get sessions:", error)
      return []
    }
  }

  async createSession(name: string, agentType: string = "orchestrator", githubUrl?: string): Promise<CodeSearchSession> {
    try {
      const sessionData: CodeSearchSessionCreate = {
        name,
        github_url: githubUrl,
        agent_type: agentType
      }
      
      const session = await this.makeRequest<CodeSearchSession>("/api/v1/code-search/sessions", {
        method: "POST",
        body: JSON.stringify(sessionData)
      })
      
      // Convert date strings to Date objects
      const formattedSession = {
        ...session,
        created_at: new Date(session.created_at),
        last_used: new Date(session.last_used),
        updated_at: new Date(session.updated_at),
        messages: []
      }
      
      // Update cache
      this.sessionsCache.unshift(formattedSession)
      this.activeSessionId = session.id
      
      return formattedSession
    } catch (error) {
      console.error("Failed to create session:", error)
      throw error
    }
  }

  async getSession(sessionId: string): Promise<CodeSearchSession | null> {
    try {
      const session = await this.makeRequest<CodeSearchSession>(`/api/v1/code-search/sessions/${sessionId}`)
      return {
        ...session,
        created_at: new Date(session.created_at),
        last_used: new Date(session.last_used),
        updated_at: new Date(session.updated_at)
      }
    } catch (error) {
      console.error("Failed to get session:", error)
      return null
    }
  }

  async updateSession(sessionId: string, updates: Partial<CodeSearchSession>): Promise<void> {
    try {
      const session = await this.makeRequest<CodeSearchSession>(`/api/v1/code-search/sessions/${sessionId}`, {
        method: "PUT",
        body: JSON.stringify(updates)
      })
      
      // Update cache
      const index = this.sessionsCache.findIndex(s => s.id === sessionId)
      if (index !== -1) {
        this.sessionsCache[index] = {
          ...session,
          created_at: new Date(session.created_at),
          last_used: new Date(session.last_used),
          updated_at: new Date(session.updated_at),
        }
      }
    } catch (error) {
      console.error("Failed to update session:", error)
    }
  }

  async deleteSession(sessionId: string): Promise<void> {
    try {
      await this.makeRequest<{ message: string }>(`/api/v1/code-search/sessions/${sessionId}`, {
        method: "DELETE"
      })
      
      // Update cache
      this.sessionsCache = this.sessionsCache.filter(s => s.id !== sessionId)
      
      if (this.activeSessionId === sessionId) {
        this.activeSessionId = this.sessionsCache.length > 0 ? this.sessionsCache[0].id : null
      }
    } catch (error) {
      console.error("Failed to delete session:", error)
    }
  }

  async getEmbeddingsStatus(sessionId: string): Promise<EmbeddingsStatus | null> {
    try {
      return await this.makeRequest<EmbeddingsStatus>(`/api/v1/code-search/sessions/${sessionId}/embeddings-status`)
    } catch (error) {
      console.error("Failed to get embeddings status:", error)
      return null
    }
  }

  async regenerateEmbeddings(sessionId: string): Promise<void> {
    try {
      await this.makeRequest<{ message: string }>(`/api/v1/code-search/sessions/${sessionId}/regenerate-embeddings`, {
        method: "POST"
      })
    } catch (error) {
      console.error("Failed to regenerate embeddings:", error)
      throw error
    }
  }

  setActiveSession(sessionId: string): void {
    this.activeSessionId = sessionId
  }

  clearActiveSession(): void {
    this.activeSessionId = null
  }

  getActiveSession(): CodeSearchSession | null {
    if (!this.activeSessionId) return null
    return this.sessionsCache.find(s => s.id === this.activeSessionId) || null
  }

  // In-memory message management based on session ID
  getSessionMessages(sessionId: string): Message[] {
    return this.messagesCache.get(sessionId) || []
  }

  addMessageToSession(sessionId: string, message: Message): void {
    const messages = this.messagesCache.get(sessionId) || []
    messages.push(message)
    this.messagesCache.set(sessionId, messages)
    
    // Update session last_used time
    const session = this.sessionsCache.find(s => s.id === sessionId)
    if (session) {
      session.last_used = new Date()
    }
  }

  updateMessageInSession(sessionId: string, messageId: string, updates: Partial<Message>): void {
    const messages = this.messagesCache.get(sessionId) || []
    const messageIndex = messages.findIndex(m => m.id === messageId)
    if (messageIndex !== -1) {
      messages[messageIndex] = {
        ...messages[messageIndex],
        ...updates
      }
      this.messagesCache.set(sessionId, messages)
    }
  }

  clearSessionMessages(sessionId: string): void {
    this.messagesCache.delete(sessionId)
  }
}

export const agentService = new AgentService() 
