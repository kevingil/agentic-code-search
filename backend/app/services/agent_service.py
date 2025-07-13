"""
Agent Service Layer
Manages A2A MCP agents and provides a clean interface for API routes
"""

import logging
from typing import Any, Dict, List, Optional, AsyncIterator
from contextlib import asynccontextmanager
import asyncio
from dataclasses import dataclass

from app.a2a_mcp.src.a2a_mcp.agents.orchestrator_agent import OrchestratorAgent
from app.a2a_mcp.src.a2a_mcp.agents.adk_travel_agent import CodeSearchAgent

logger = logging.getLogger(__name__)

@dataclass
class AgentConfig:
    """Configuration for an agent"""
    agent_type: str
    agent_name: str
    description: str
    instructions: str
    capabilities: List[str]

class AgentService:
    """Service for managing A2A MCP agents"""
    
    def __init__(self):
        self.orchestrator_agent: Optional[OrchestratorAgent] = None
        self.code_search_agents: Dict[str, CodeSearchAgent] = {}
        self.agent_configs: Dict[str, AgentConfig] = {}
        self._initialize_configs()
    
    def _initialize_configs(self):
        """Initialize agent configurations"""
        self.agent_configs = {
            # We can get these from the agent cards
            "orchestrator": AgentConfig(
                agent_type="orchestrator",
                agent_name="Orchestrator Agent",
                description="Orchestrates complex code search and analysis tasks",
                instructions="You are an orchestrator agent that manages complex code search and analysis tasks by coordinating with specialized agents.",
                capabilities=["task_orchestration", "agent_coordination", "workflow_management"]
            ),
            "code_search": AgentConfig(
                agent_type="code_search",
                agent_name="Code Search Agent",
                description="Performs semantic code search and analysis across codebases",
                instructions="You are an expert code search agent. Help users find relevant code patterns, functions, and implementations across codebases using semantic search.",
                capabilities=["semantic_search", "pattern_matching", "code_analysis"]
            ),
            "code_analysis": AgentConfig(
                agent_type="code_analysis",
                agent_name="Code Analysis Agent",
                description="Performs static code analysis and code quality assessment",
                instructions="You are an expert code analysis agent. Help users analyze code quality, identify patterns, suggest improvements, and detect potential issues.",
                capabilities=["static_analysis", "code_quality", "refactoring_suggestions"]
            ),
            "code_documentation": AgentConfig(
                agent_type="code_documentation",
                agent_name="Code Documentation Agent",
                description="Generates and analyzes code documentation and comments",
                instructions="You are an expert code documentation agent. Help users create comprehensive documentation, docstrings, and comments for their code.",
                capabilities=["documentation_generation", "docstring_creation", "code_comments"]
            )
        }
    
    async def get_orchestrator_agent(self) -> OrchestratorAgent:
        """Get or create the orchestrator agent"""
        if self.orchestrator_agent is None:
            logger.info("Initializing orchestrator agent")
            self.orchestrator_agent = OrchestratorAgent()
        return self.orchestrator_agent
    
    async def get_code_search_agent(self, agent_type: str) -> CodeSearchAgent:
        """Get or create a code search agent by type"""
        if agent_type not in self.code_search_agents:
            if agent_type not in self.agent_configs:
                raise ValueError(f"Unknown agent type: {agent_type}")
            
            config = self.agent_configs[agent_type]
            logger.info(f"Initializing code search agent: {agent_type}")
            
            self.code_search_agents[agent_type] = CodeSearchAgent(
                agent_name=config.agent_name,
                description=config.description,
                instructions=config.instructions
            )
        
        return self.code_search_agents[agent_type]
    
    async def get_agent_by_type(self, agent_type: str):
        """Get an agent by type (orchestrator or code search agent)"""
        if agent_type == "orchestrator":
            return await self.get_orchestrator_agent()
        elif agent_type in self.agent_configs and agent_type != "orchestrator":
            return await self.get_code_search_agent(agent_type)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
    
    async def query_agent(
        self, 
        agent_type: str, 
        query: str, 
        context_id: str, 
        task_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Query an agent and return streaming responses"""
        try:
            agent = await self.get_agent_by_type(agent_type)
            
            # Stream responses from the agent
            async for chunk in agent.stream(query, context_id, task_id):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error querying agent {agent_type}: {e}")
            yield {
                "response_type": "error",
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"Error: {str(e)}"
            }
    
    async def get_agent_status(self, agent_type: str) -> Dict[str, Any]:
        """Get the status of a specific agent"""
        if agent_type not in self.agent_configs:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        config = self.agent_configs[agent_type]
        
        # Check if agent is initialized
        is_active = False
        if agent_type == "orchestrator":
            is_active = self.orchestrator_agent is not None
        else:
            is_active = agent_type in self.code_search_agents
        
        return {
            "agent_name": config.agent_name,
            "agent_type": config.agent_type,
            "status": "active" if is_active else "inactive",
            "description": config.description,
            "capabilities": config.capabilities,
            "is_active": is_active
        }
    
    async def get_all_agents_status(self) -> List[Dict[str, Any]]:
        """Get status of all available agents"""
        agents_status = []
        
        for agent_type in self.agent_configs:
            status = await self.get_agent_status(agent_type)
            agents_status.append(status)
        
        return agents_status
    
    async def clear_agent_context(self, context_id: str) -> Dict[str, str]:
        """Clear the context/state for a specific session"""
        try:
            # Clear orchestrator context
            if self.orchestrator_agent:
                self.orchestrator_agent.clear_state()
            
            # Clear code search agents context
            for agent in self.code_search_agents.values():
                # If agents have context clearing methods, call them here
                pass
            
            return {
                "status": "success",
                "message": f"Context {context_id} cleared successfully"
            }
        except Exception as e:
            logger.error(f"Error clearing context {context_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to clear context: {str(e)}"
            }
    
    async def generate_code_search_summary(self, context_id: str) -> Dict[str, Any]:
        """Generate a summary of code search results for a specific context"""
        try:
            orchestrator = await self.get_orchestrator_agent()
            
            # Generate summary using orchestrator
            summary = await orchestrator.generate_summary()
            
            return {
                "context_id": context_id,
                "summary": summary,
                "status": "completed"
            }
        except Exception as e:
            logger.error(f"Error generating code search summary: {e}")
            return {
                "context_id": context_id,
                "summary": "Failed to generate summary",
                "status": "error",
                "error": str(e)
            }
    
    async def perform_code_search(
        self, 
        query: str, 
        context_id: str, 
        task_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Perform a comprehensive code search using the orchestrator"""
        try:
            orchestrator = await self.get_orchestrator_agent()
            
            # Use orchestrator to coordinate the code search
            async for chunk in orchestrator.stream(query, context_id, task_id):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error performing code search: {e}")
            yield {
                "response_type": "error",
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"Error: {str(e)}"
            }


# Global agent service instance
agent_service = AgentService() 
