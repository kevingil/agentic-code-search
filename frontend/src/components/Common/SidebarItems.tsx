import { Box, Flex, Icon, Text, VStack, HStack, IconButton } from "@chakra-ui/react"
import { useQueryClient } from "@tanstack/react-query"
import { Link as RouterLink, useRouterState } from "@tanstack/react-router"
import { FiBriefcase, FiHome, FiSearch, FiSettings, FiUsers, FiPlus, FiTrash2, FiGithub } from "react-icons/fi"
import { useState, useEffect } from "react"
import type { IconType } from "react-icons/lib"

import type { UserPublic } from "@/client"
import { agentService, type CodeSearchSession } from "@/services/agentService"

const items = [
  { icon: FiSearch, title: "Code Search", path: "/code-search" },
  { icon: FiHome, title: "Dashboard", path: "/dashboard" },
  { icon: FiBriefcase, title: "Items", path: "/items" },
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

const SidebarItems = ({ onClose }: SidebarItemsProps) => {
  const queryClient = useQueryClient()
  const currentUser = queryClient.getQueryData<UserPublic>(["currentUser"])
  const router = useRouterState()
  const [sessions, setSessions] = useState<CodeSearchSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)

  const isCodeSearchRoute = router.location.pathname === "/code-search"

  const finalItems: Item[] = currentUser?.is_superuser
    ? [...items, { icon: FiUsers, title: "Admin", path: "/admin" }]
    : items

  useEffect(() => {
    loadSessions()
  }, [])

  // Listen for session changes and updates
  useEffect(() => {
    const handleSessionListUpdate = () => {
      loadSessions()
    }

    window.addEventListener('sessionListChanged', handleSessionListUpdate)
    return () => {
      window.removeEventListener('sessionListChanged', handleSessionListUpdate)
    }
  }, [])

  const loadSessions = () => {
    const loadedSessions = agentService.getSessions()
    setSessions(loadedSessions)
    
    const activeSession = agentService.getActiveSession()
    setActiveSessionId(activeSession?.id || null)
  }

  const handleNewSession = () => {
    // Clear the active session to show the repo picker
    agentService.clearActiveSession()
    setActiveSessionId(null)
    
    // Trigger the main panel to show repo picker
    window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId: null } }))
    window.dispatchEvent(new CustomEvent('showRepoPicker'))
  }

  const handleSelectSession = (sessionId: string) => {
    agentService.setActiveSession(sessionId)
    setActiveSessionId(sessionId)
    
    // Trigger refresh of code search component
    if (isCodeSearchRoute) {
      window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId } }))
    }
  }

  const handleDeleteSession = (sessionId: string) => {
    agentService.deleteSession(sessionId)
    loadSessions()
    
    // Notify other components about session list changes
    window.dispatchEvent(new CustomEvent('sessionListChanged'))
    
    // Trigger refresh of code search component
    if (isCodeSearchRoute) {
      window.dispatchEvent(new CustomEvent('sessionChanged', { detail: { sessionId: null } }))
    }
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
        bg={router.location.pathname === path ? "blue.50" : "transparent"}
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

      {/* Sessions Section - only show on code search route */}
      {isCodeSearchRoute && (
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
          <Box maxH="300px" overflowY="auto" px={2}>
            {sessions.length === 0 ? (
              <Text fontSize="sm" color="gray.500" px={2} py={4} textAlign="center">
                No sessions yet
              </Text>
            ) : (
              sessions.map((session) => (
                <Flex
                  key={session.id}
                  align="center"
                  justify="space-between"
                  px={2}
                  py={2}
                  bg={activeSessionId === session.id ? "blue.50" : "transparent"}
                  borderRadius="md"
                  _hover={{ bg: "gray.50" }}
                  cursor="pointer"
                  onClick={() => handleSelectSession(session.id)}
                >
                  <VStack align="start" gap={1} flex={1} minW={0}>
                    <Text fontSize="sm" fontWeight="medium" truncate>
                      {session.name}
                    </Text>
                    <HStack gap={1}>
                      <Text fontSize="xs" color="gray.500">
                        {session.messages.length} messages
                      </Text>
                      {session.github_url && (
                        <>
                          <Text fontSize="xs" color="gray.400">•</Text>
                          <Icon as={FiGithub} boxSize={3} color="gray.500" />
                        </>
                      )}
                    </HStack>
                  </VStack>
                  
                  <IconButton
                    size="sm"
                    variant="ghost"
                    aria-label="Delete Session"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDeleteSession(session.id)
                    }}
                  >
                    <FiTrash2 size={12} />
                  </IconButton>
                </Flex>
              ))
            )}
          </Box>
        </Box>
      )}
    </VStack>
  )
}

export default SidebarItems
