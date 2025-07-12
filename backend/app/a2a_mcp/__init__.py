"""
A2A MCP (Agent-to-Agent Model Context Protocol) Package
"""

# Import main components
from .src.a2a_mcp.agents import OrchestratorAgent, TravelAgent
from .src.a2a_mcp.common import BaseAgent

__version__ = "0.1.0"
__all__ = [
    "OrchestratorAgent",
    "TravelAgent", 
    "BaseAgent",
] 
