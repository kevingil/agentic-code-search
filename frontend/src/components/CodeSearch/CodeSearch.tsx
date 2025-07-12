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
} from "@chakra-ui/react"
import { FiSearch, FiCode, FiUser, FiTrash2, FiMessageSquare } from "react-icons/fi"

import { Button } from "@/components/ui/button"
import { agentService, type AgentQueryRequest, type StreamChunk } from "@/services/agentService"

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

interface ConversationHistory {
  messages: Message[]
  contextId: string
  agentType: string
}

function CodeSearch() {
  const [query, setQuery] = useState("")
  const [isSearching, setIsSearching] = useState(false)
  const [conversation, setConversation] = useState<ConversationHistory>({
    messages: [],
    contextId: `context_${Date.now()}`,
    agentType: "orchestrator", // Default to orchestrator agent
  })
  const [availableAgents, setAvailableAgents] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom when new messages are added
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [conversation.messages])

  // Load available agents on component mount
  useEffect(() => {
    loadAvailableAgents()
  }, [])

  const loadAvailableAgents = async () => {
    try {
      const agents = await agentService.getAgentsStatus()
      setAvailableAgents(agents.filter(agent => agent.is_active).map(agent => agent.agent_type))
    } catch (error) {
      console.error("Failed to load agents:", error)
      // Fallback to default agents
      setAvailableAgents(["orchestrator"])
    }
  }

  const handleSearch = async () => {
    if (!query.trim()) return

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

    setConversation(prev => ({
      ...prev,
      messages: [...prev.messages, userMessage, agentMessage],
    }))

    setIsSearching(true)
    const currentQuery = query
    setQuery("")

    try {
      const request: AgentQueryRequest = {
        query: currentQuery,
        context_id: conversation.contextId,
        agent_type: conversation.agentType,
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
        setConversation(prev => ({
          ...prev,
          messages: prev.messages.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  content: fullContent,
                  status: chunk.is_task_complete ? "complete" : "streaming",
                  metadata: {
                    ...lastMetadata,
                    artifacts: extractArtifacts(fullContent),
                  },
                }
              : msg
          ),
        }))
      }

      // Final update
      setConversation(prev => ({
        ...prev,
        messages: prev.messages.map(msg =>
          msg.id === agentMessageId
            ? {
                ...msg,
                content: fullContent,
                status: "complete",
                metadata: {
                  ...lastMetadata,
                  artifacts: extractArtifacts(fullContent),
                },
              }
            : msg
        ),
      }))

    } catch (error) {
      console.error("Search failed:", error)
      
      // Update agent message with error
      setConversation(prev => ({
        ...prev,
        messages: prev.messages.map(msg =>
          msg.id === agentMessageId
            ? {
                ...msg,
                content: `Error: ${error instanceof Error ? error.message : "Unknown error occurred"}`,
                status: "error",
              }
            : msg
        ),
      }))

      console.error("Search failed:", error)
    } finally {
      setIsSearching(false)
    }
  }

  const extractArtifacts = (content: string): any[] => {
    // Simple artifact extraction - look for code blocks
    const codeBlocks = content.match(/```[\s\S]*?```/g) || []
    return codeBlocks.map((block, index) => ({
      id: `artifact_${index}`,
      type: "code",
      content: block,
    }))
  }

  const handleClearConversation = async () => {
    try {
      await agentService.clearAgentContext(conversation.contextId)
      setConversation({
        messages: [],
        contextId: `context_${Date.now()}`,
        agentType: conversation.agentType,
      })
      console.log("Conversation cleared successfully")
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
    setConversation(prev => ({
      ...prev,
      agentType,
    }))
  }

  const formatMessageContent = (content: string) => {
    // Simple formatting - split by code blocks and render appropriately
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
    <Container maxW="6xl" py={8}>
      <VStack gap={8} align="stretch">
        {/* Header */}
        <Box textAlign="center" mb={8}>
          <Heading size="xl" mb={4}>
            Agentic Code Search
          </Heading>
          <Text fontSize="lg" color="gray.600">
            Ask questions about your codebase and let our AI agent find the answers
          </Text>
        </Box>

        {/* Agent Selection & Controls */}
        <Flex justify="space-between" align="center" p={4} bg="gray.50" rounded="md">
          <HStack>
            <Text fontWeight="medium">Agent:</Text>
            <select
              value={conversation.agentType}
              onChange={(e) => handleAgentTypeChange(e.target.value)}
              style={{
                padding: "8px 12px",
                borderRadius: "6px",
                border: "1px solid #e2e8f0",
                backgroundColor: "white",
              }}
            >
              {availableAgents.map(agent => (
                <option key={agent} value={agent}>
                  {agent.replace("_", " ").replace(/\b\w/g, l => l.toUpperCase())}
                </option>
              ))}
            </select>
          </HStack>
          <Button
            onClick={handleClearConversation}
            variant="outline"
            size="sm"
            disabled={conversation.messages.length === 0}
          >
            <FiTrash2 />
            Clear Conversation
          </Button>
        </Flex>

        {/* Conversation History */}
        {conversation.messages.length > 0 && (
          <VStack gap={4} align="stretch">
            <Heading size="md">Conversation</Heading>
            <Box maxH="600px" overflowY="auto" border="1px" borderColor="gray.200" rounded="md" p={4}>
                             {conversation.messages.map((message, index) => (
                 <Box key={message.id} mb={index === conversation.messages.length - 1 ? 0 : 6}>
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

        {/* Search Input */}
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

        {/* Empty State */}
        {conversation.messages.length === 0 && (
          <Box textAlign="center" py={12}>
            <FiSearch size={48} style={{ margin: "0 auto 16px" }} />
            <Text fontSize="lg" color="gray.500">
              Ask a question about your codebase to get started
            </Text>
          </Box>
        )}
      </VStack>
    </Container>
  )
}

export default CodeSearch 
