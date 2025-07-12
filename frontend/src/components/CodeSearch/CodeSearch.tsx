import React, { useState } from "react"
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
import { FiSearch, FiCode, FiUser } from "react-icons/fi"

import { Button } from "@/components/ui/button"

interface SearchResult {
  id: string
  question: string
  status: "searching" | "complete" | "error"
  results?: {
    summary: string
    files: string[]
    analysis: string
  }
}

function CodeSearch() {
  const [query, setQuery] = useState("")
  const [isSearching, setIsSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])

  const handleSearch = async () => {
    if (!query.trim()) return

    const searchId = Date.now().toString()
    const newSearch: SearchResult = {
      id: searchId,
      question: query,
      status: "searching",
    }

    setSearchResults(prev => [newSearch, ...prev])
    setIsSearching(true)
    setQuery("")

    // Simulate API call - replace with actual API integration later
    setTimeout(() => {
      setSearchResults(prev => prev.map(result => 
        result.id === searchId 
          ? {
              ...result,
              status: "complete",
              results: {
                summary: "Found relevant code patterns related to your query.",
                files: ["src/components/Auth.tsx", "src/hooks/useAuth.ts", "src/api/auth.ts"],
                analysis: "The authentication system uses JWT tokens with refresh capabilities. The main authentication logic is handled through React hooks and context providers."
              }
            }
          : result
      ))
      setIsSearching(false)
    }, 3000)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
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

        {/* Search Results */}
        {searchResults.length > 0 && (
          <VStack gap={6} align="stretch">
            <Heading size="md">Search Results</Heading>
            {searchResults.map((result) => (
              <Box key={result.id} border="1px" borderColor="gray.200" borderRadius="md" p={6}>
                <VStack align="stretch" gap={4}>
                  {/* Question */}
                  <HStack justify="space-between">
                    <HStack>
                      <FiUser />
                      <Text fontWeight="medium">You asked:</Text>
                    </HStack>
                    <Badge
                      colorScheme={
                        result.status === "complete" ? "green" : 
                        result.status === "searching" ? "blue" : "red"
                      }
                    >
                      {result.status === "complete" ? "Complete" : 
                       result.status === "searching" ? "Searching" : "Error"}
                    </Badge>
                  </HStack>
                  <Text bg="gray.50" p={3} rounded="md">
                    {result.question}
                  </Text>

                  {/* Loading State */}
                  {result.status === "searching" && (
                    <Flex align="center" justify="center" py={8}>
                      <VStack gap={4}>
                        <Spinner size="xl" color="blue.500" />
                        <Text>AI agent is analyzing your codebase...</Text>
                      </VStack>
                    </Flex>
                  )}

                  {/* Results */}
                  {result.status === "complete" && result.results && (
                    <VStack align="stretch" gap={4}>
                      <HStack>
                        <FiCode />
                        <Text fontWeight="medium">Agent Response:</Text>
                      </HStack>
                      
                      <Box bg="blue.50" p={4} rounded="md">
                        <Text fontWeight="medium" mb={2}>Summary:</Text>
                        <Text>{result.results.summary}</Text>
                      </Box>

                      <Box>
                        <Text fontWeight="medium" mb={2}>Relevant Files:</Text>
                        <VStack align="start" gap={1}>
                          {result.results.files.map((file, index) => (
                            <Badge key={index} variant="outline" colorScheme="blue">
                              {file}
                            </Badge>
                          ))}
                        </VStack>
                      </Box>

                      <Box>
                        <Text fontWeight="medium" mb={2}>Analysis:</Text>
                        <Text bg="gray.50" p={3} rounded="md">
                          {result.results.analysis}
                        </Text>
                      </Box>
                    </VStack>
                  )}
                </VStack>
              </Box>
            ))}
          </VStack>
        )}

        {/* Empty State */}
        {searchResults.length === 0 && (
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
