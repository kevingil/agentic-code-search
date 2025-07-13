import { Flex, Image, useBreakpointValue } from "@chakra-ui/react"
import { Link } from "@tanstack/react-router"

import { isLoggedIn } from "@/hooks/useAuth"
import Logo from "/assets/images/code-search-logo.png"
import UserMenu from "./UserMenu"

function Navbar() {
  const display = useBreakpointValue({ base: "none", md: "flex" })
  const logoLink = isLoggedIn() ? "/code-search" : "/"

  return (
    <Flex
      display={display}
      justify="space-between"
      color="white"
      align="center"
      bg="bg.muted"
      w="100%"
      top={0}
      p={4}
    >
      <Link to={logoLink}>
        <div style={{ display: "flex", alignItems: "center", gap: "2px", cursor: "pointer" }}>
          <p style={{ color: "#33025b", fontSize: "1.5rem", fontWeight: "bold", cursor: "pointer" }}>Code Search</p>
        </div>
      </Link>
      <Flex gap={2} alignItems="center">
        <UserMenu />
      </Flex>
    </Flex>
  )
}

export default Navbar
