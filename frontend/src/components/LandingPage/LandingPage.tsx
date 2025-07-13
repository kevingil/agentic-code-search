import React from "react"
import {
  Box,
  Container,
  Heading,
  Text,
  VStack,
  HStack,
  Image,
  SimpleGrid,
  Icon,
} from "@chakra-ui/react"
import { Link as RouterLink } from "@tanstack/react-router"
import { FiSearch, FiCode, FiZap, FiUsers, FiShield, FiTrendingUp } from "react-icons/fi"

import { Button } from "@/components/ui/button"
import Logo from "/assets/images/code-search-logo.png"

function LandingPage() {
  return (
    <Box>
      {/* Header */}
      <Box bg="white" borderBottom="1px" borderColor="gray.200" py={4}>
        <Container maxW="6xl">
          <HStack justify="space-between">
            <HStack>
              <Image src={Logo} alt="Logo" height="40px" />
              <Heading size="md">Code Search</Heading>
            </HStack>
            <HStack gap={4}>
              <Button asChild variant="ghost">
                <RouterLink to="/login">Log In</RouterLink>
              </Button>
              <Button asChild>
                <RouterLink to="/signup">Sign Up</RouterLink>
              </Button>
            </HStack>
          </HStack>
        </Container>
      </Box>

      {/* Hero Section */}
      <Box bg="gradient-to-r from-blue-50 to-purple-50" py={20}>
        <Container maxW="6xl">
          <VStack gap={8} textAlign="center">
            <Heading size="2xl" maxW="4xl">
              Ask Questions About Your Codebase,
              <Text as="span" color="blue.600"> Get Instant Answers</Text>
            </Heading>
            <Text fontSize="xl" color="gray.600" maxW="2xl">
              Our AI agent understands your code and can answer complex questions about 
              architecture, patterns, and implementation details in seconds.
            </Text>
            <HStack gap={4}>
              <Button asChild size="lg">
                <RouterLink to="/signup">Get Started Free</RouterLink>
              </Button>
              <Button asChild size="lg" variant="outline">
                <RouterLink to="/login">Sign In</RouterLink>
              </Button>
            </HStack>
          </VStack>
        </Container>
      </Box>

      {/* Features */}
      <Box py={20}>
        <Container maxW="6xl">
          <VStack gap={16}>
            <VStack gap={4} textAlign="center">
              <Heading size="lg">Intelligent Code Analysis</Heading>
              <Text fontSize="lg" color="gray.600" maxW="2xl">
                Go beyond simple text search. Our AI agent understands code relationships, 
                patterns, and architecture to provide meaningful insights.
              </Text>
            </VStack>

            <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} gap={8}>
              <Box border="1px" borderColor="gray.200" borderRadius="md" p={6}>
                <VStack align="start" gap={4}>
                  <Icon as={FiSearch} boxSize={8} color="blue.500" />
                  <Heading size="md">Natural Language Queries</Heading>
                  <Text>
                    Ask questions in plain English: "How does authentication work?" 
                    or "Where is the payment processing logic?"
                  </Text>
                </VStack>
              </Box>

              <Box border="1px" borderColor="gray.200" borderRadius="md" p={6}>
                <VStack align="start" gap={4}>
                  <Icon as={FiCode} boxSize={8} color="green.500" />
                  <Heading size="md">Code Context Understanding</Heading>
                  <Text>
                    The AI agent analyzes code relationships, dependencies, and patterns 
                    to provide comprehensive answers with relevant file references.
                  </Text>
                </VStack>
              </Box>

              <Box border="1px" borderColor="gray.200" borderRadius="md" p={6}>
                <VStack align="start" gap={4}>
                  <Icon as={FiZap} boxSize={8} color="purple.500" />
                  <Heading size="md">Lightning Fast</Heading>
                  <Text>
                    Get answers in seconds, not hours. No more manual code exploration 
                    or digging through documentation.
                  </Text>
                </VStack>
              </Box>

              <Box border="1px" borderColor="gray.200" borderRadius="md" p={6}>
                <VStack align="start" gap={4}>
                  <Icon as={FiUsers} boxSize={8} color="orange.500" />
                  <Heading size="md">Team Collaboration</Heading>
                  <Text>
                    Share insights with your team and build a knowledge base of 
                    your codebase's architecture and patterns.
                  </Text>
                </VStack>
              </Box>

              <Box border="1px" borderColor="gray.200" borderRadius="md" p={6}>
                <VStack align="start" gap={4}>
                  <Icon as={FiShield} boxSize={8} color="red.500" />
                  <Heading size="md">Secure & Private</Heading>
                  <Text>
                    Your code stays private and secure. All analysis happens 
                    in your environment with enterprise-grade security.
                  </Text>
                </VStack>
              </Box>

              <Box border="1px" borderColor="gray.200" borderRadius="md" p={6}>
                <VStack align="start" gap={4}>
                  <Icon as={FiTrendingUp} boxSize={8} color="teal.500" />
                  <Heading size="md">Continuous Learning</Heading>
                  <Text>
                    The AI agent learns from your codebase patterns and improves 
                    its answers over time.
                  </Text>
                </VStack>
              </Box>
            </SimpleGrid>
          </VStack>
        </Container>
      </Box>

      {/* CTA Section */}
      <Box bg="blue.600" py={20}>
        <Container maxW="6xl">
          <VStack gap={8} textAlign="center">
            <Heading size="lg" color="white">
              Ready to Transform Your Code Exploration?
            </Heading>
            <Text fontSize="lg" color="blue.100" maxW="2xl">
              Join thousands of developers who are already using AI to understand 
              their codebases better.
            </Text>
            <Button asChild size="lg" variant="solid">
              <RouterLink to="/signup">Start Free Trial</RouterLink>
            </Button>
          </VStack>
        </Container>
      </Box>

      {/* Footer */}
      <Box bg="gray.900" color="white" py={8}>
        <Container maxW="6xl">
          <HStack justify="space-between">
            <HStack>
              <Image src={Logo} alt="Logo" height="30px" />
              <Text>&copy; 2024 Code Search. All rights reserved.</Text>
            </HStack>
            <HStack gap={6}>
              <Text fontSize="sm">Privacy Policy</Text>
              <Text fontSize="sm">Terms of Service</Text>
              <Text fontSize="sm">Contact</Text>
            </HStack>
          </HStack>
        </Container>
      </Box>
    </Box>
  )
}

export default LandingPage 
