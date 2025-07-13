import React, { useState, useEffect, useRef } from "react"
import {
  Box,
  Container,
  Input,
  VStack,
  HStack,
  Text,
  Heading,
  Textarea,
  Flex,
  Badge,
  Spinner,
  Link,
  IconButton,
  Image,
} from "@chakra-ui/react"
import { FiSearch, FiUser, FiTrash2, FiMessageSquare, FiGithub, FiPlus, FiEdit3, FiExternalLink } from "react-icons/fi"

import { Button } from "@/components/ui/button"
import { agentService, type AgentQueryRequest, type StreamChunk, type CodeSearchSession } from "@/services/agentService"
import Logo from "/assets/images/code-search-logo.png"

interface Message {
  id: string
  type: "user" | "agent"
  content: string
  timestamp: Date
  status: "sending" | "streaming" | "complete" | "error"
  metadata?: {
    response_type?: string
    is_task_complete?: boolean
    require_user_input?: boolean
    artifacts?: any[]
  }
}

// Utility function to extract repo name from GitHub URL
const extractRepoNameFromUrl = (url: string): string | null => {
  try {
    // Remove trailing slash
    const cleanUrl = url.replace(/\/$/, "")
    
    // Handle different GitHub URL formats
    const patterns = [
      /github\.com\/([^\/]+)\/([^\/]+)$/,  // https://github.com/owner/repo
      /github\.com\/([^\/]+)\/([^\/]+)\/tree\/.*$/,  // https://github.com/owner/repo/tree/branch
      /github\.com\/([^\/]+)\/([^\/]+)\/.*$/,  // https://github.com/owner/repo/anything
    ]
    
    for (const pattern of patterns) {
      const match = cleanUrl.match(pattern)
      if (match) {
        return `${match[1]}/${match[2]}`
      }
    }
    
    return null
  } catch (error) {
    return null
  }
}

// Validate GitHub URL
const isValidGithubUrl = (url: string): boolean => {
  try {
    const urlObj = new URL(url)
    return urlObj.hostname === 'github.com' && extractRepoNameFromUrl(url) !== null
  } catch {
    return false
  }
}

function CodeSearch() {
  const [query, setQuery] = useState("")
  const [isSearching, setIsSearching] = useState(false)
  const [currentSession, setCurrentSession] = useState<CodeSearchSession | null>(null)
  const [availableAgents, setAvailableAgents] = useState<string[]>([])
  const [githubUrl, setGithubUrl] = useState("")
  const [urlError, setUrlError] = useState<string | null>(null)
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom when new messages are added
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [currentSession?.messages])

  // Load available agents and session on component mount
  useEffect(() => {
    loadAvailableAgents()
    loadCurrentSession()
  }, [])

  // Listen for session changes from sidebar
  useEffect(() => {
    const handleSessionChange = (event: CustomEvent) => {
      const { sessionId } = event.detail
      if (sessionId) {
        loadSessionById(sessionId)
      } else {
        setCurrentSession(null)
      }
    }

    // Listen for session list changes to refresh current session data
    const handleSessionListChange = () => {
      if (currentSession) {
        // Refresh current session data
        const updatedSession = agentService.getSession(currentSession.id)
        if (updatedSession) {
          setCurrentSession(updatedSession)
        } else {
          // Session was deleted
          setCurrentSession(null)
        }
      }
    }

    // Listen for repo picker requests from sidebar
    const handleShowRepoPicker = () => {
      setCurrentSession(null)
      // Clear any form state
      setGithubUrl("")
      setUrlError(null)
      setIsCreatingSession(false)
    }

    window.addEventListener('sessionChanged', handleSessionChange as EventListener)
    window.addEventListener('sessionListChanged', handleSessionListChange)
    window.addEventListener('showRepoPicker', handleShowRepoPicker)
    
    return () => {
      window.removeEventListener('sessionChanged', handleSessionChange as EventListener)
      window.removeEventListener('sessionListChanged', handleSessionListChange)
      window.removeEventListener('showRepoPicker', handleShowRepoPicker)
    }
  }, [currentSession])

  const loadAvailableAgents = async () => {
    try {
      const agents = await agentService.getAgentsStatus()
      setAvailableAgents(agents.filter(agent => agent.is_active).map(agent => agent.agent_type))
    } catch (error) {
      console.error("Failed to load agents:", error)
      setAvailableAgents(["orchestrator"])
    }
  }

  const loadCurrentSession = () => {
    const activeSession = agentService.getActiveSession()
    setCurrentSession(activeSession)
  }

  const loadSessionById = (sessionId: string) => {
    const session = agentService.getSession(sessionId)
    setCurrentSession(session)
  }

  const handleCreateSession = async () => {
    if (!githubUrl.trim()) {
      setUrlError("Please enter a GitHub URL")
      return
    }

    if (!isValidGithubUrl(githubUrl.trim())) {
      setUrlError("Please enter a valid GitHub repository URL")
      return
    }

    setIsCreatingSession(true)
    setUrlError(null)

    try {
      const repoName = extractRepoNameFromUrl(githubUrl.trim())
      if (!repoName) {
        setUrlError("Could not extract repository name from URL")
        return
      }

      const session = agentService.createSession(
        repoName,
        "orchestrator",
        githubUrl.trim()
      )
      
      setCurrentSession(session)
      setGithubUrl("")
      
      // Notify sidebar and other components about session changes
      window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId: session.id } }))
      window.dispatchEvent(new CustomEvent('sessionListChanged'))
      
    } catch (error) {
      console.error("Failed to create session:", error)
      setUrlError("Failed to create session. Please try again.")
    } finally {
      setIsCreatingSession(false)
    }
  }

  const handleCreateQuickSession = () => {
    const session = agentService.createSession(
      `Session ${new Date().toLocaleString()}`,
      "orchestrator"
    )
    setCurrentSession(session)
    
    // Notify sidebar and other components about session changes
    window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId: session.id } }))
    window.dispatchEvent(new CustomEvent('sessionListChanged'))
  }

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const url = e.target.value
    setGithubUrl(url)
    setUrlError(null)
  }

  const handleUrlKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault()
      handleCreateSession()
    }
  }

  const handleSearch = async () => {
    if (!query.trim()) return

    // Create a new session if none exists
    if (!currentSession) {
      handleCreateQuickSession()
      // Wait a bit for the session to be created
      setTimeout(() => {
        if (query.trim()) {
          handleSearch()
        }
      }, 100)
      return
    }

    if (!currentSession) return

    const userMessageId = `msg_${Date.now()}`
    const agentMessageId = `msg_${Date.now() + 1}`

    // Add user message
    const userMessage: Message = {
      id: userMessageId,
      type: "user",
      content: query,
      timestamp: new Date(),
      status: "complete",
    }

    // Add agent message placeholder
    const agentMessage: Message = {
      id: agentMessageId,
      type: "agent",
      content: "",
      timestamp: new Date(),
      status: "streaming",
      metadata: { artifacts: [] },
    }

    // Add messages to session
    agentService.addMessageToSession(currentSession.id, userMessage)
    agentService.addMessageToSession(currentSession.id, agentMessage)

    // Update local state
    setCurrentSession(prev => prev ? {
      ...prev,
      messages: [...prev.messages, userMessage, agentMessage]
    } : null)

    // Notify sidebar about session updates
    window.dispatchEvent(new CustomEvent('sessionListChanged'))

    setIsSearching(true)
    const currentQuery = query
    setQuery("")

    try {
      const request: AgentQueryRequest = {
        query: currentQuery,
        context_id: currentSession.id,
        agent_type: currentSession.agent_type,
        github_url: currentSession.github_url,
      }

      // Stream the agent response
      let fullContent = ""
      let lastMetadata: any = {}

      for await (const chunk of agentService.streamAgentQuery(request)) {
        if (chunk.error) {
          throw new Error(chunk.error)
        }

        if (chunk.content) {
          fullContent += chunk.content
        }

        lastMetadata = {
          response_type: chunk.response_type,
          is_task_complete: chunk.is_task_complete,
          require_user_input: chunk.require_user_input,
        }

        // Update the agent message with streaming content
        const updatedMessage = {
          content: fullContent,
          status: chunk.is_task_complete ? "complete" as const : "streaming" as const,
          metadata: {
            ...lastMetadata,
            artifacts: extractArtifacts(fullContent),
          },
        }

        agentService.updateMessageInSession(currentSession.id, agentMessageId, updatedMessage)
        
        setCurrentSession(prev => prev ? {
          ...prev,
          messages: prev.messages.map(msg =>
            msg.id === agentMessageId ? { ...msg, ...updatedMessage } : msg
          )
        } : null)
      }

      // Final update
      const finalMessage = {
        content: fullContent,
        status: "complete" as const,
        metadata: {
          ...lastMetadata,
          artifacts: extractArtifacts(fullContent),
        },
      }

      agentService.updateMessageInSession(currentSession.id, agentMessageId, finalMessage)
      
      setCurrentSession(prev => prev ? {
        ...prev,
        messages: prev.messages.map(msg =>
          msg.id === agentMessageId ? { ...msg, ...finalMessage } : msg
        )
      } : null)

      // Notify sidebar about session updates
      window.dispatchEvent(new CustomEvent('sessionListChanged'))

    } catch (error) {
      console.error("Search failed:", error)
      
      // Update agent message with error
      const errorMessage = {
        content: `Error: ${error instanceof Error ? error.message : "Unknown error occurred"}`,
        status: "error" as const,
      }

      agentService.updateMessageInSession(currentSession.id, agentMessageId, errorMessage)
      
      setCurrentSession(prev => prev ? {
        ...prev,
        messages: prev.messages.map(msg =>
          msg.id === agentMessageId ? { ...msg, ...errorMessage } : msg
        )
      } : null)

      // Notify sidebar about session updates
      window.dispatchEvent(new CustomEvent('sessionListChanged'))
    } finally {
      setIsSearching(false)
    }
  }

  const extractArtifacts = (content: string): any[] => {
    const codeBlocks = content.match(/```[\s\S]*?```/g) || []
    return codeBlocks.map((block, index) => ({
      id: `artifact_${index}`,
      type: "code",
      content: block,
    }))
  }

  const handleClearConversation = async () => {
    if (!currentSession) return

    try {
      await agentService.clearAgentContext(currentSession.id)
      agentService.updateSession(currentSession.id, { messages: [] })
      setCurrentSession(prev => prev ? { ...prev, messages: [] } : null)
      
      // Notify sidebar about session updates
      window.dispatchEvent(new CustomEvent('sessionListChanged'))
    } catch (error) {
      console.error("Failed to clear conversation:", error)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }

  const handleAgentTypeChange = (agentType: string) => {
    if (!currentSession) return
    
    agentService.updateSession(currentSession.id, { agent_type: agentType })
    setCurrentSession(prev => prev ? { ...prev, agent_type: agentType } : null)
    
    // Notify sidebar about session updates
    window.dispatchEvent(new CustomEvent('sessionListChanged'))
  }

  const formatMessageContent = (content: string) => {
    const parts = content.split(/(```[\s\S]*?```)/g)
    return parts.map((part, index) => {
      if (part.startsWith("```")) {
        return (
          <Box key={index} bg="gray.900" color="white" p={4} rounded="md" my={2} overflow="auto">
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              <code>{part.slice(3, -3)}</code>
            </pre>
          </Box>
        )
      }
      return (
        <Text key={index} whiteSpace="pre-wrap">
          {part}
        </Text>
      )
    })
  }

  return (
    <Box>
      {/* Sticky Session Info Bar - only show when there's an active session */}
      {currentSession && (
        <Box
          position="sticky"
          top={0}
          bg="white"
          borderBottom="1px"
          borderColor="gray.200"
          zIndex={10}
          py={2}
          px={4}
        >
          <Container maxW="6xl">
            <Flex justify="space-between" align="center">
              <HStack gap={3}>
                <FiMessageSquare color="gray.600" />
                <Text fontWeight="medium" fontSize="sm" color="gray.800">
                  {currentSession.name}
                </Text>
                {currentSession.github_url && (
                  <>
                    <Text color="gray.400">•</Text>
                    <Link href={currentSession.github_url} target="_blank" rel="noopener noreferrer">
                      <HStack gap={1}>
                        <FiGithub color="gray.600" />
                        <Text fontSize="sm" color="blue.500">
                          {currentSession.github_url.replace('https://github.com/', '')}
                        </Text>
                        <FiExternalLink size={10} color="gray.500" />
                      </HStack>
                    </Link>
                  </>
                )}
              </HStack>
              
              <IconButton
                onClick={handleClearConversation}
                variant="ghost"
                size="sm"
                disabled={currentSession.messages.length === 0}
                aria-label="Clear Conversation"
                title="Clear Conversation"
              >
                <FiTrash2 size={16} />
              </IconButton>
            </Flex>
          </Container>
        </Box>
      )}

      <Container maxW="6xl" py={8}>
        <VStack gap={8} align="stretch">
          {/* Repo Picker - shown when no session is active */}
          {!currentSession && (
            <Box maxW="2xl" mx="auto" minH="70vh" display="flex" flexDirection="column">
              <VStack gap={4} align="stretch" flex={1}>
                {/* Combined Header + GitHub Repository Option */}
                <Box borderRadius="lg" p={6} bg="white">
                  <VStack gap={4} align="stretch">
                    {/* Header Section */}
                    <VStack gap={3} align="center" mb={2}>
                      <Image src={Logo} alt="Code Search Logo" h="120px" />
                      <Heading size="lg" color="#33025b">
                        Agentic Code Search
                      </Heading>
                      <Text fontSize="md" color="gray.600" textAlign="center">
                        Ask questions about your codebase and let our AI agent find the answers
                      </Text>
                    </VStack>
                    
                    {/* GitHub Repository Form */}
                    <Box pt={4} borderTop="1px" borderColor="gray.100">
                      <Text fontSize="sm" color="gray.600" textAlign="center" mb={4}>
                        Connect a GitHub repository to start analyzing your code
                      </Text>
                      
                      <HStack>
                        <Input
                          placeholder="https://github.com/username/repository"
                          value={githubUrl}
                          onChange={handleUrlChange}
                          onKeyPress={handleUrlKeyPress}
                          size="lg"
                          flex={1}
                          borderColor={urlError ? "red.300" : "gray.200"}
                        />
                      </HStack>
                      
                      {urlError && (
                        <Box bg="red.50" p={3} rounded="md" border="1px" borderColor="red.200" mt={3}>
                          <Text color="red.600" fontSize="sm">{urlError}</Text>
                        </Box>
                      )}

                      <Button
                        onClick={handleCreateSession}
                        disabled={!githubUrl.trim() || isCreatingSession}
                        colorScheme="blue"
                        size="lg"
                        w="full"
                        mt={4}
                      >
                        <FiPlus />
                        {isCreatingSession ? "Creating..." : "Analyze Repository"}
                      </Button>
                    </Box>
                  </VStack>
                </Box>

                {/* General Session Option - Secondary */}
                <Box border="1px" borderColor="gray.200" borderRadius="lg" p={4} bg="white" shadow="sm">
                  <HStack gap={4} align="center">
                    <Box p={2} bg="purple.50" borderRadius="full">
                      <FiMessageSquare size={20} color="#805AD5" />
                    </Box>
                    <VStack align="start" flex={1} gap={1}>
                      <Text fontWeight="semibold" fontSize="md">
                        General Session
                      </Text>
                      <Text fontSize="sm" color="gray.600">
                        Start a conversation without connecting to a specific repository
                      </Text>
                    </VStack>
                    <Button
                      onClick={handleCreateQuickSession}
                      variant="outline"
                      colorScheme="purple"
                      size="md"
                    >
                      <FiMessageSquare />
                      Start Session
                    </Button>
                  </HStack>
                </Box>

                {/* Spacer to push footer to bottom */}
                <Box flex={1} />

                {/* Popular Repositories - Footer */}
                <Box p={4} mt={4}>
                  <Text fontSize="sm" color="gray.600" mb={3} textAlign="center">
                    Or try these popular repositories:
                  </Text>
                  <HStack justify="center" gap={2} flexWrap="wrap">
                    {[
                      "facebook/react",
                      "microsoft/vscode",
                      "vercel/next.js",
                      "nodejs/node"
                    ].map(repo => (
                      <Button
                        key={repo}
                        variant="outline"
                        size="sm"
                        onClick={() => setGithubUrl(`https://github.com/${repo}`)}
                        bg="white"
                        borderRadius="2xl"
                        borderColor="gray.200"
                        _hover={{ bg: "blue.50", borderColor: "blue.300" }}
                      >
                        <FiGithub size={14} />
                        {repo}
                      </Button>
                    ))}
                  </HStack>
                </Box>
              </VStack>
            </Box>
          )}

          {/* Conversation History */}
          {currentSession && currentSession.messages.length > 0 && (
            <VStack gap={4} align="stretch">
              <Heading size="md">Conversation</Heading>
              <Box maxH="600px" overflowY="auto" border="1px" borderColor="gray.200" rounded="md" p={4}>
                {currentSession.messages.map((message, index) => (
                  <Box key={message.id} mb={index === currentSession.messages.length - 1 ? 0 : 6}>
                    <HStack justify="space-between" mb={2}>
                      <HStack>
                        {message.type === "user" ? <FiUser /> : <FiMessageSquare />}
                        <Text fontWeight="medium">
                          {message.type === "user" ? "You" : "Agent"}
                        </Text>
                        <Text fontSize="sm" color="gray.500">
                          {message.timestamp.toLocaleTimeString()}
                        </Text>
                      </HStack>
                      <Badge
                        colorScheme={
                          message.status === "complete" ? "green" :
                          message.status === "streaming" ? "blue" :
                          message.status === "error" ? "red" : "gray"
                        }
                      >
                        {message.status}
                      </Badge>
                    </HStack>
                    
                    <Box
                      bg={message.type === "user" ? "blue.50" : "gray.50"}
                      p={4}
                      rounded="md"
                      border="1px"
                      borderColor={message.type === "user" ? "blue.200" : "gray.200"}
                    >
                      {message.status === "streaming" && !message.content ? (
                        <Flex align="center" gap={2}>
                          <Spinner size="sm" />
                          <Text>Agent is thinking...</Text>
                        </Flex>
                      ) : message.status === "error" ? (
                        <Box bg="red.50" p={3} rounded="md" border="1px" borderColor="red.200">
                          <Text color="red.600" fontWeight="medium">Error!</Text>
                          <Text color="red.600">{message.content}</Text>
                        </Box>
                      ) : (
                        <Box>{formatMessageContent(message.content)}</Box>
                      )}
                    </Box>
                  </Box>
                ))}
                <div ref={messagesEndRef} />
              </Box>
            </VStack>
          )}

          {/* Search Input - only show when there's an active session */}
          {currentSession && (
            <Box border="1px" borderColor="gray.200" borderRadius="md" p={6}>
              <VStack gap={4}>
                <Textarea
                  placeholder="Ask a question about your codebase... (e.g., 'How does user authentication work?', 'Where is the payment processing logic?')"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  rows={3}
                  resize="vertical"
                />
                <HStack justify="space-between" w="full">
                  <Text fontSize="sm" color="gray.500">
                    Press Enter to search, Shift+Enter for new line
                  </Text>
                  <Button
                    onClick={handleSearch}
                    disabled={!query.trim() || isSearching}
                    colorScheme="blue"
                  >
                    <FiSearch />
                    {isSearching ? "Searching..." : "Search"}
                  </Button>
                </HStack>
              </VStack>
            </Box>
          )}
        </VStack>
      </Container>
    </Box>
  )
}

export default CodeSearch 
