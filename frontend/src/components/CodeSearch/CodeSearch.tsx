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
    parsed_content?: {
      type: 'input_required' | 'artifact' | 'message'
      data: any
    }
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
        const parsedContent = parseAgentContent(fullContent)
        const updatedMessage = {
          content: fullContent,
          status: chunk.is_task_complete ? "complete" as const : "streaming" as const,
          metadata: {
            ...lastMetadata,
            artifacts: extractArtifacts(fullContent),
            parsed_content: parsedContent,
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
      const parsedContent = parseAgentContent(fullContent)
      const finalMessage = {
        content: fullContent,
        status: "complete" as const,
        metadata: {
          ...lastMetadata,
          artifacts: extractArtifacts(fullContent),
          parsed_content: parsedContent,
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
    const artifacts: any[] = []
    
    // Check if content contains input_required JSON - if so, don't extract it as an artifact
    try {
      const jsonMatch = content.match(/\{[\s\S]*?\}/g)
      if (jsonMatch) {
        for (const match of jsonMatch) {
          try {
            const parsed = JSON.parse(match)
            if (parsed && typeof parsed === 'object' && parsed.status === 'input_required') {
              // Don't extract input_required JSON as artifacts
              continue
            }
          } catch (e) {
            // Not valid JSON, continue
          }
        }
      }
    } catch (e) {
      // Continue with normal processing
    }
    
    // Try to parse entire content as JSON first to check for structured responses
    try {
      const parsed = JSON.parse(content.trim())
      if (parsed && typeof parsed === 'object') {
        // If it's a structured JSON response, treat it as an artifact unless it's input_required
        if (parsed.status !== 'input_required') {
          artifacts.push({
            id: `artifact_json_${Date.now()}`,
            type: "json",
            content: parsed,
          })
        }
        return artifacts
      }
    } catch (e) {
      // Not pure JSON, continue with other parsing
    }
    
    // Extract code blocks (but skip any that contain input_required JSON)
    const codeBlocks = content.match(/```[\s\S]*?```/g) || []
    codeBlocks.forEach((block, index) => {
      // Check if this code block contains input_required JSON
      try {
        const codeContent = block.slice(3, -3).trim()
        const parsed = JSON.parse(codeContent)
        if (parsed && typeof parsed === 'object' && parsed.status === 'input_required') {
          return // Skip this code block
        }
      } catch (e) {
        // Not JSON or not input_required, include it
      }
      
      artifacts.push({
        id: `artifact_code_${index}`,
        type: "code",
        content: block,
      })
    })
    
    // Check for JSON blocks in the content and exclude input_required ones
    const jsonPattern = /\{[\s\S]*?\}/g
    const jsonMatches = [...content.matchAll(jsonPattern)]
    jsonMatches.forEach((match, index) => {
      try {
        const parsed = JSON.parse(match[0])
        if (parsed && typeof parsed === 'object' && parsed.status !== 'input_required') {
          // Only add non-input_required JSON as artifacts
          artifacts.push({
            id: `artifact_json_inline_${index}`,
            type: "json",
            content: parsed,
          })
        }
      } catch (e) {
        // Not valid JSON, skip
      }
    })
    
    // Extract file paths or structured data patterns
    const filePathPattern = /(?:^|\s)([a-zA-Z0-9_-]+\/[a-zA-Z0-9_/.,-]+\.[a-zA-Z0-9]+)(?:\s|$)/gm
    const filePaths = [...content.matchAll(filePathPattern)]
    if (filePaths.length > 3) { // Only if there are multiple file paths
      artifacts.push({
        id: `artifact_files_${Date.now()}`,
        type: "file_list",
        content: filePaths.map(match => match[1]),
      })
    }
    
    return artifacts
  }

  const parseAgentContent = (content: string) => {
    // Try to parse as JSON first
    try {
      const parsed = JSON.parse(content)
      if (parsed && typeof parsed === 'object') {
        if (parsed.status === 'input_required' && parsed.question) {
          return {
            type: 'input_required' as const,
            data: parsed
          }
        } else {
          return {
            type: 'artifact' as const,
            data: parsed
          }
        }
      }
    } catch (e) {
      // Not JSON, treat as regular message
    }
    
    return {
      type: 'message' as const,
      data: content
    }
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      if (e.ctrlKey || e.metaKey) {
        // Ctrl+Enter (Windows/Linux) or Cmd+Enter (macOS): always submit
        e.preventDefault()
        handleSearch()
      } else if (!e.shiftKey) {
        // Enter alone: submit
        e.preventDefault()
        handleSearch()
      }
      // Shift+Enter: do nothing (default behavior for new line)
    }
  }

  const handleAgentTypeChange = (agentType: string) => {
    if (!currentSession) return
    
    agentService.updateSession(currentSession.id, { agent_type: agentType })
    setCurrentSession(prev => prev ? { ...prev, agent_type: agentType } : null)
    
    // Notify sidebar about session updates
    window.dispatchEvent(new CustomEvent('sessionListChanged'))
  }

  const renderArtifact = (artifact: any) => {
    switch (artifact.type) {
      case "code":
        return (
          <Box key={artifact.id} bg="gray.900" color="white" p={4} rounded="md" my={2} overflow="auto">
            <HStack justify="space-between" mb={2}>
              <Text fontSize="sm" color="gray.300">Code Block</Text>
              <Button
                size="xs"
                variant="ghost"
                colorScheme="gray"
                onClick={() => navigator.clipboard.writeText(artifact.content.slice(3, -3))}
              >
                Copy
              </Button>
            </HStack>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              <code>{artifact.content.slice(3, -3)}</code>
            </pre>
          </Box>
        )
      
      case "json":
        return (
          <Box key={artifact.id} bg="blue.50" border="1px" borderColor="blue.200" p={4} rounded="md" my={2}>
            <HStack justify="space-between" mb={2}>
              <Text fontSize="sm" color="blue.700" fontWeight="medium">Structured Data</Text>
              <Button
                size="xs"
                variant="ghost"
                colorScheme="blue"
                onClick={() => navigator.clipboard.writeText(JSON.stringify(artifact.content, null, 2))}
              >
                Copy JSON
              </Button>
            </HStack>
            <Box bg="white" p={3} rounded="md" overflow="auto">
              <pre style={{ margin: 0, fontSize: "14px" }}>
                <code>{JSON.stringify(artifact.content, null, 2)}</code>
              </pre>
            </Box>
          </Box>
        )
      
      case "file_list":
        return (
          <Box key={artifact.id} bg="green.50" border="1px" borderColor="green.200" p={4} rounded="md" my={2}>
            <Text fontSize="sm" color="green.700" fontWeight="medium" mb={2}>Related Files</Text>
            <VStack align="start" gap={1}>
              {artifact.content.map((file: string, index: number) => (
                <Text key={index} fontSize="sm" fontFamily="mono" color="green.800">
                  {file}
                </Text>
              ))}
            </VStack>
          </Box>
        )
      
      default:
        return null
    }
  }

  const formatMessageContent = (message: Message) => {
    const content = message.content
    
    // Check if content contains input_required JSON and extract just the question text
    const jsonPattern = /\{[\s\S]*?\}/g
    const jsonMatches = [...content.matchAll(jsonPattern)]
    let hasInputRequired = false
    let questionText = null
    
    for (const match of jsonMatches) {
      try {
        const parsed = JSON.parse(match[0])
        if (parsed && typeof parsed === 'object' && parsed.status === 'input_required' && parsed.question) {
          hasInputRequired = true
          questionText = parsed.question
          break
        }
      } catch (e) {
        // Not valid JSON, continue
      }
    }
    
    // If we found input_required JSON, show it as a normal message with just the question
    if (hasInputRequired && questionText) {
      // Extract any text content (removing the JSON part and cleaning up)
      let textContent = content
      for (const match of jsonMatches) {
        try {
          const parsed = JSON.parse(match[0])
          if (parsed && typeof parsed === 'object' && parsed.status === 'input_required') {
            textContent = textContent.replace(match[0], '').trim()
          }
        } catch (e) {
          // Continue
        }
      }
      
      // Clean up any remaining JSON fragments, code markers, etc.
      textContent = textContent
        .replace(/```json/g, '')
        .replace(/```/g, '')
        .replace(/^\s*json\s*$/gm, '')
        .replace(/\n\s*\n/g, '\n')
        .trim()
      
      // If text content just says the question, don't duplicate it
      if (textContent.includes(questionText)) {
        return <Text whiteSpace="pre-wrap">{textContent}</Text>
      }
      
      // Combine text content with question, removing any redundant parts
      const finalText = textContent && questionText 
        ? `${textContent}\n\n${questionText}` 
        : questionText || textContent
      
      return (
        <Text whiteSpace="pre-wrap">{finalText}</Text>
      )
    }
    
    // Check if this is a pure input_required response
    try {
      const parsed = JSON.parse(content.trim())
      if (parsed && typeof parsed === 'object' && parsed.status === 'input_required' && parsed.question) {
        return (
          <Text whiteSpace="pre-wrap">{parsed.question}</Text>
        )
      }
    } catch (e) {
      // Not pure JSON or not input_required, continue with other logic
    }
    
    // Handle parsed content types from metadata
    if (message.metadata?.parsed_content) {
      const { type, data } = message.metadata.parsed_content
      
      if (type === 'input_required') {
        return (
          <Text whiteSpace="pre-wrap">{data.question}</Text>
        )
      }
      
      if (type === 'artifact') {
        return (
          <VStack align="stretch" gap={2}>
            <Text>The agent provided structured data:</Text>
            {renderArtifact({ id: 'parsed_artifact', type: 'json', content: data })}
          </VStack>
        )
      }
    }
    
    // Default message formatting with artifacts
    const artifacts = message.metadata?.artifacts || []
    
    // If we have artifacts, show content and artifacts separately
    if (artifacts.length > 0) {
      const parts = content.split(/(```[\s\S]*?```)/g)
      const textParts = parts.filter(part => !part.startsWith("```"))
      const textContent = textParts.join("").trim()
      
      return (
        <VStack align="stretch" gap={3}>
          {textContent && (
            <Text whiteSpace="pre-wrap">{textContent}</Text>
          )}
          {artifacts.map(artifact => renderArtifact(artifact))}
        </VStack>
      )
    }
    
    // Fallback to original formatting
    const parts = content.split(/(```[\s\S]*?```)/g)
    return parts.map((part, index) => {
      if (part.startsWith("```")) {
        return renderArtifact({ id: `inline_code_${index}`, type: 'code', content: part })
      }
      return (
        <Text key={index} whiteSpace="pre-wrap">
          {part}
        </Text>
      )
    })
  }

  return (
    <Box h="full" display="flex" flexDirection="column" position="relative">
      {/* Sticky Session Info Bar - only show when there's an active session */}
      {currentSession && (
        <Box
          bg="white"
          borderBottom="1px"
          borderColor="gray.200"
          py={2}
          px={4}
          flexShrink={0}
        >
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
        </Box>
      )}

      {/* Main Content Area */}
      <Box flex={1} overflow="hidden">
        {/* Repo Picker - shown when no session is active */}
        {!currentSession && (
          <Box h="full" display="flex" flexDirection="column" p={4}>
            <Box maxW="2xl" mx="auto" h="full" display="flex" flexDirection="column">
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
                        colorScheme="purple"
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
                        _hover={{ bg: "purple.50", borderColor: "purple.300" }}
                      >
                        <FiGithub size={14} />
                        {repo}
                      </Button>
                    ))}
                  </HStack>
                </Box>
              </VStack>
            </Box>
          </Box>
        )}

        {/* Conversation History - when session is active */}
        {currentSession && (
          <Box h="full" overflow="auto" pb="210px" px={4}>
            <Box maxW="4xl" mx="auto" py={4}>
              {currentSession.messages.length === 0 ? (
                <Box textAlign="center" py={12}>
                  <VStack gap={4}>
                    <FiMessageSquare size={48} color="gray.300" />
                    <Text fontSize="lg" color="gray.500">
                      Start a conversation
                    </Text>
                    <Text fontSize="sm" color="gray.400">
                      Ask a question about your codebase to get started
                    </Text>
                  </VStack>
                </Box>
              ) : (
                <VStack gap={4} align="stretch">
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
                          <Box>{formatMessageContent(message)}</Box>
                        )}
                      </Box>
                    </Box>
                  ))}
                  <div ref={messagesEndRef} />
                </VStack>
              )}
            </Box>
          </Box>
        )}
      </Box>

      {/* Fixed Chat Input at Bottom - only show when there's an active session */}
      {currentSession && (
        <Box
          position="fixed"
          display="flex"
          justifyContent="center"
          alignItems="center"
          bottom={4}
          left={{ base: 4, md: "calc(320px + 2rem)" }}
          right={4}
          bg="white"
          borderTop="1px"
          borderColor="gray.200"
        >
          <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          bg="white"
          borderTop="1px"
          borderColor="gray.200"
          shadow="xl"
          rounded="md"
          border="1px"
          w="100%"
          p={4}
          maxW="6xl"
        >
          <Box w="100%" mx="auto">
            <VStack gap={3}>
              <Textarea
                placeholder="Ask a question about your codebase... (e.g., 'How does user authentication work?', 'Where is the payment processing logic?')"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={4}
                resize="none"
                h="140px"
                maxH="140px"
                bg="transparent"
                border="none"
                outline="none"
                fontSize="xl"
                _focus={{ 
                  outline: "none",
                  boxShadow: "none"
                }}
                _placeholder={{
                  color: "gray.400"
                }}
              />
              <HStack justify="space-between" w="full">
                <Text fontSize="sm" color="gray.500">
                  Shift+Enter for new line
                </Text>
                <Button
                  onClick={handleSearch}
                  disabled={!query.trim() || isSearching}
                  colorScheme="purple"
                  size="sm"
                >
                  <FiSearch />
                  {isSearching ? "Searching..." : "Search"}
                </Button>
              </HStack>
            </VStack>
          </Box>
          </Box>
        </Box>
      )}
    </Box>
  )
}

export default CodeSearch 
