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
from app.a2a_mcp.src.a2a_mcp.agents.adk_travel_agent import TravelAgent

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
        self.travel_agents: Dict[str, TravelAgent] = {}
        self.agent_configs: Dict[str, AgentConfig] = {}
        self._initialize_configs()
    
    def _initialize_configs(self):
        """Initialize agent configurations"""
        self.agent_configs = {
            "orchestrator": AgentConfig(
                agent_type="orchestrator",
                agent_name="Orchestrator Agent",
                description="Orchestrates the task generation and execution",
                instructions="You are an orchestrator agent that manages complex travel planning tasks by coordinating with specialized agents.",
                capabilities=["task_orchestration", "agent_coordination", "workflow_management"]
            ),
            "air_ticketing": AgentConfig(
                agent_type="air_ticketing",
                agent_name="Air Ticketing Agent",
                description="Specializes in finding and booking air tickets",
                instructions="You are an expert air ticketing agent. Help users find and book flights based on their requirements. Use the available tools to search for flights and provide booking options.",
                capabilities=["flight_search", "booking", "price_comparison"]
            ),
            "hotel_booking": AgentConfig(
                agent_type="hotel_booking",
                agent_name="Hotel Booking Agent",
                description="Specializes in finding and booking hotels",
                instructions="You are an expert hotel booking agent. Help users find and book hotels based on their requirements. Use the available tools to search for hotels and provide booking options.",
                capabilities=["hotel_search", "booking", "amenities_comparison"]
            ),
            "car_rental": AgentConfig(
                agent_type="car_rental",
                agent_name="Car Rental Agent",
                description="Specializes in finding and booking car rentals",
                instructions="You are an expert car rental agent. Help users find and book rental cars based on their requirements. Use the available tools to search for rental cars and provide booking options.",
                capabilities=["car_search", "rental_booking", "location_services"]
            )
        }
    
    async def get_orchestrator_agent(self) -> OrchestratorAgent:
        """Get or create the orchestrator agent"""
        if self.orchestrator_agent is None:
            logger.info("Initializing orchestrator agent")
            self.orchestrator_agent = OrchestratorAgent()
        return self.orchestrator_agent
    
    async def get_travel_agent(self, agent_type: str) -> TravelAgent:
        """Get or create a travel agent by type"""
        if agent_type not in self.travel_agents:
            if agent_type not in self.agent_configs:
                raise ValueError(f"Unknown agent type: {agent_type}")
            
            config = self.agent_configs[agent_type]
            logger.info(f"Initializing travel agent: {agent_type}")
            
            self.travel_agents[agent_type] = TravelAgent(
                agent_name=config.agent_name,
                description=config.description,
                instructions=config.instructions
            )
        
        return self.travel_agents[agent_type]
    
    async def get_agent_by_type(self, agent_type: str):
        """Get an agent by type (orchestrator or travel agent)"""
        if agent_type == "orchestrator":
            return await self.get_orchestrator_agent()
        elif agent_type in self.agent_configs and agent_type != "orchestrator":
            return await self.get_travel_agent(agent_type)
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
        if not query.strip():
            raise ValueError("Query cannot be empty")
        
        agent = await self.get_agent_by_type(agent_type)
        
        async for chunk in agent.stream(query, context_id, task_id):
            yield chunk
    
    async def get_agent_status(self, agent_type: str) -> Dict[str, Any]:
        """Get status information for an agent"""
        if agent_type not in self.agent_configs:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        config = self.agent_configs[agent_type]
        
        # Check if agent is initialized
        is_initialized = False
        if agent_type == "orchestrator":
            is_initialized = self.orchestrator_agent is not None
        else:
            is_initialized = agent_type in self.travel_agents
        
        return {
            "agent_name": config.agent_name,
            "agent_type": agent_type,
            "description": config.description,
            "capabilities": config.capabilities,
            "status": "initialized" if is_initialized else "not_initialized",
            "is_active": is_initialized
        }
    
    async def get_all_agents_status(self) -> List[Dict[str, Any]]:
        """Get status of all configured agents"""
        status_list = []
        for agent_type in self.agent_configs:
            status = await self.get_agent_status(agent_type)
            status_list.append(status)
        return status_list
    
    async def clear_agent_context(self, context_id: str) -> Dict[str, str]:
        """Clear context for all agents that match the context ID"""
        cleared = []
        
        # Clear orchestrator context if it matches
        if self.orchestrator_agent and self.orchestrator_agent.context_id == context_id:
            self.orchestrator_agent.clear_state()
            cleared.append("orchestrator")
        
        # Travel agents don't maintain context state in the same way,
        # but we can reinitialize them if needed
        
        return {
            "message": f"Context {context_id} cleared successfully",
            "cleared_agents": cleared
        }
    
    async def generate_travel_summary(self, context_id: str) -> Dict[str, Any]:
        """Generate a travel summary using the orchestrator agent"""
        orchestrator = await self.get_orchestrator_agent()
        
        if orchestrator.context_id != context_id:
            raise ValueError(f"No active context found for {context_id}")
        
        summary = await orchestrator.generate_summary()
        
        return {
            "context_id": context_id,
            "summary": summary,
            "travel_context": orchestrator.travel_context,
            "query_history": orchestrator.query_history,
            "results": orchestrator.results
        }
    
    async def plan_travel(
        self, 
        query: str, 
        context_id: str, 
        task_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Plan travel using the orchestrator agent"""
        # Enhance query with travel planning context
        enhanced_query = f"Plan a travel itinerary: {query}"
        
        # Use orchestrator agent for travel planning
        async for chunk in self.query_agent("orchestrator", enhanced_query, context_id, task_id):
            yield chunk

# Global agent service instance
agent_service = AgentService() 
