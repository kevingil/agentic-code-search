import { Box, Flex, Icon, Text, VStack, HStack, IconButton, Badge, Spinner } from "@chakra-ui/react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link as RouterLink, useRouterState, useNavigate } from "@tanstack/react-router"
import { FiSearch, FiSettings, FiUsers, FiPlus, FiTrash2, FiGithub, FiRefreshCw, FiDatabase } from "react-icons/fi"
import type { IconType } from "react-icons/lib"

import type { UserPublic } from "@/client"
import { agentService, type CodeSearchSession, type EmbeddingsStatus } from "@/services/agentService"

const items = [
  { icon: FiSearch, title: "Code Search", path: "/code-search" },
  { icon: FiSettings, title: "User Settings", path: "/settings" },
]

interface SidebarItemsProps {
  onClose?: () => void
}

interface Item {
  icon: IconType
  title: string
  path: string
}

function getSessionsQueryOptions() {
  return {
    queryFn: () => agentService.getSessions(),
    queryKey: ["sessions"],
    staleTime: 30000, // Consider data fresh for 30 seconds
  }
}

function getEmbeddingsStatusQueryOptions(sessionId: string) {
  return {
    queryFn: () => agentService.getEmbeddingsStatus(sessionId),
    queryKey: ["embeddings-status", sessionId],
    enabled: !!sessionId,
    staleTime: 60000, // Consider data fresh for 1 minute
  }
}

const SidebarItems = ({ onClose }: SidebarItemsProps) => {
  const queryClient = useQueryClient()
  const currentUser = queryClient.getQueryData<UserPublic>(["currentUser"])
  const router = useRouterState()
  const navigate = useNavigate()

  const isCodeSearchRoute = router.location.pathname === "/code-search"
  const activeSession = agentService.getActiveSession()
  const activeSessionId = activeSession?.id || null

  const finalItems: Item[] = currentUser?.is_superuser
    ? [...items, { icon: FiUsers, title: "Admin", path: "/admin" }]
    : items

  // Fetch sessions using React Query
  const { 
    data: sessions = [], 
    isLoading: sessionsLoading,
    error: sessionsError 
  } = useQuery(getSessionsQueryOptions())

  // Mutations for session operations
  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: string) => agentService.deleteSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      window.dispatchEvent(new CustomEvent('sessionListChanged'))
    },
  })

  const regenerateEmbeddingsMutation = useMutation({
    mutationFn: (sessionId: string) => agentService.regenerateEmbeddings(sessionId),
    onSuccess: (_, sessionId) => {
      queryClient.invalidateQueries({ queryKey: ["embeddings-status", sessionId] })
    },
  })

  const handleNewSession = () => {
    // Clear the active session to show the repo picker
    agentService.clearActiveSession()
    
    // Trigger the main panel to show repo picker
    window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId: null } }))
    window.dispatchEvent(new CustomEvent('showRepoPicker'))
  }

  const handleSelectSession = (sessionId: string) => {
    agentService.setActiveSession(sessionId)
    
    // Navigate to code search route if not already there
    if (!isCodeSearchRoute) {
      navigate({ to: "/code-search" })
    } else {
      // Trigger refresh of code search component if already on the route
      window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId } }))
    }
  }

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (window.confirm("Are you sure you want to delete this session?")) {
      try {
        await deleteSessionMutation.mutateAsync(sessionId)
        
        // If deleted session was active, clear it
        if (activeSessionId === sessionId) {
          agentService.clearActiveSession()
          window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId: null } }))
        }
      } catch (error) {
        console.error("Failed to delete session:", error)
      }
    }
  }

  const handleRegenerateEmbeddings = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await regenerateEmbeddingsMutation.mutateAsync(sessionId)
    } catch (error) {
      console.error("Failed to regenerate embeddings:", error)
    }
  }

  const formatRelativeTime = (date: Date) => {
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return "Just now"
    if (minutes < 60) return `${minutes}m ago`
    if (hours < 24) return `${hours}h ago`
    if (days < 7) return `${days}d ago`
    return date.toLocaleDateString()
  }

  const listItems = finalItems.map(({ icon, title, path }) => (
    <RouterLink key={title} to={path} onClick={onClose}>
      <Flex
        gap={4}
        px={4}
        py={2}
        _hover={{
          background: "gray.subtle",
        }}
        alignItems="center"
        fontSize="sm"
        bg={router.location.pathname === path ? "purple.50" : "transparent"}
        borderRadius="md"
        mx={2}
      >
        <Icon as={icon} alignSelf="center" />
        <Text ml={2}>{title}</Text>
      </Flex>
    </RouterLink>
  ))

  return (
    <VStack align="stretch" gap={4}>
      <Box>
        <Text fontSize="xs" px={4} py={2} fontWeight="bold">
          Menu
        </Text>
        <Box>{listItems}</Box>
      </Box>

      <Box>
        <HStack justify="space-between" px={4} py={2}>
          <Text fontSize="xs" fontWeight="bold">
            Sessions
          </Text>
          <IconButton
            size="sm"
            variant="ghost"
            aria-label="New Session"
            onClick={handleNewSession}
            title="Create New Session"
          >
            <FiPlus size={14} />
          </IconButton>
        </HStack>

        {/* Sessions List */}
        <Box maxH="400px" overflowY="auto" px={2}>
          {sessionsLoading ? (
            <Flex justify="center" py={4}>
              <Spinner size="sm" />
            </Flex>
          ) : sessionsError ? (
            <Text fontSize="sm" color="red.500" px={2} py={4} textAlign="center">
              Failed to load sessions
            </Text>
          ) : sessions.length === 0 ? (
            <Text fontSize="sm" color="gray.500" px={2} py={4} textAlign="center">
              No sessions yet
            </Text>
          ) : (
            sessions.map((session) => <SessionItem 
              key={session.id} 
              session={session}
              isActive={activeSessionId === session.id}
              onSelect={handleSelectSession}
              onDelete={handleDeleteSession}
              onRegenerateEmbeddings={handleRegenerateEmbeddings}
              formatRelativeTime={formatRelativeTime}
              isRegenerating={regenerateEmbeddingsMutation.isPending}
            />)
          )}
        </Box>
      </Box>
    </VStack>
  )
}

interface SessionItemProps {
  session: CodeSearchSession
  isActive: boolean
  onSelect: (sessionId: string) => void
  onDelete: (sessionId: string, e: React.MouseEvent) => void
  onRegenerateEmbeddings: (sessionId: string, e: React.MouseEvent) => void
  formatRelativeTime: (date: Date) => string
  isRegenerating: boolean
}

function SessionItem({ 
  session, 
  isActive, 
  onSelect, 
  onDelete, 
  onRegenerateEmbeddings, 
  formatRelativeTime,
  isRegenerating 
}: SessionItemProps) {
  const { data: embeddingsStatus } = useQuery(
    getEmbeddingsStatusQueryOptions(session.github_url ? session.id : "")
  )

  return (
    <Flex
      align="center"
      justify="space-between"
      px={2}
      py={3}
      bg={isActive ? "purple.50" : "transparent"}
      borderRadius="md"
      _hover={{ bg: "gray.50" }}
      cursor="pointer"
      onClick={() => onSelect(session.id)}
      borderBottom="1px"
      borderColor="gray.100"
    >
      <VStack align="start" gap={1} flex={1} minW={0}>
        <Text fontSize="sm" fontWeight="medium" truncate>
          {session.name}
        </Text>
        
        <HStack gap={2} wrap="wrap">
          <Text fontSize="xs" color="gray.500">
            {session.messages?.length || 0} messages
          </Text>
          
          <Text fontSize="xs" color="gray.500">
            {formatRelativeTime(session.last_used)}
          </Text>
          
          {session.github_url && (
            <HStack gap={1}>
              <Icon as={FiGithub} boxSize={3} color="gray.500" />
              <Text fontSize="xs" color="gray.500" truncate maxW="120px">
                {session.github_url.replace('https://github.com/', '')}
              </Text>
            </HStack>
          )}
          
          {session.github_url && embeddingsStatus && (
            <HStack gap={1}>
              <Icon as={FiDatabase} boxSize={3} color="gray.500" />
              <Text fontSize="xs" color="gray.500">
                {embeddingsStatus.embeddings_count} embeddings
              </Text>
              <Badge 
                size="sm" 
                colorScheme={embeddingsStatus.embeddings_processed ? "green" : "yellow"}
              >
                {embeddingsStatus.embeddings_processed ? "Ready" : "Processing"}
              </Badge>
            </HStack>
          )}
        </HStack>
      </VStack>
      
      <HStack>
        {session.github_url && (
          <IconButton
            size="sm"
            variant="ghost"
            aria-label="Regenerate Embeddings"
            onClick={(e) => onRegenerateEmbeddings(session.id, e)}
            title="Regenerate Embeddings"
            loading={isRegenerating}
          >
            <FiRefreshCw size={12} />
          </IconButton>
        )}
        
        <IconButton
          size="sm"
          variant="ghost"
          aria-label="Delete Session"
          onClick={(e) => onDelete(session.id, e)}
          title="Delete Session"
        >
          <FiTrash2 size={12} />
        </IconButton>
      </HStack>
    </Flex>
  )
}

export default SidebarItems
