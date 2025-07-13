# type: ignore

import json
import logging
import sys

from pathlib import Path

import click
import httpx
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import BasePushNotificationSender, InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import AgentCard
from ..common import prompts
from ..common.agent_executor import GenericAgentExecutor
from .adk_travel_agent import CodeSearchAgent  # Renamed from TravelAgent
from .langgraph_planner_agent import LangraphPlannerAgent
from .orchestrator_agent import OrchestratorAgent


logger = logging.getLogger(__name__)


def get_agent(agent_card: AgentCard):
    """Get the agent, given an agent card."""
    try:
        print(f"DEBUG: Creating agent for card: {agent_card.name}")
        
        if agent_card.name == 'orchestrator_agent':
            print(f"DEBUG: Initializing Orchestrator Agent")
            return OrchestratorAgent()
        if agent_card.name == 'planner_agent':
            print(f"DEBUG: Initializing Planner Agent")
            return LangraphPlannerAgent()
        if agent_card.name == 'code_search_agent':
            print(f"DEBUG: Initializing Code Search Agent")
            return CodeSearchAgent(
                agent_name='code_search_agent',
                description='Performs semantic code search and analysis across codebases',
                instructions=prompts.CODE_SEARCH_INSTRUCTIONS,
            )
        if agent_card.name == 'code_analysis_agent':
            print(f"DEBUG: Initializing Code Analysis Agent")
            return CodeSearchAgent(
                agent_name='code_analysis_agent',
                description='Performs static code analysis and code quality assessment',
                instructions=prompts.CODE_ANALYSIS_INSTRUCTIONS,
            )
        if agent_card.name == 'code_documentation_agent':
            print(f"DEBUG: Initializing Code Documentation Agent")
            return CodeSearchAgent(
                agent_name='code_documentation_agent',
                description='Generates and analyzes code documentation and comments',
                instructions=prompts.CODE_DOCUMENTATION_INSTRUCTIONS,
            )
    except Exception as e:
        print(f"DEBUG: Error creating agent: {e}")
        print(f"DEBUG: Error type: {type(e)}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        raise e


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10101)
@click.option('--agent-card', 'agent_card')
def main(host, port, agent_card):
    """Starts an Agent server."""
    try:
        print(f"DEBUG: Starting agent server with card: {agent_card}")
        
        if not agent_card:
            raise ValueError('Agent card is required')
            
        print(f"DEBUG: Reading agent card file: {agent_card}")
        with Path.open(agent_card) as file:
            data = json.load(file)
        agent_card = AgentCard(**data)
        print(f"DEBUG: Agent card loaded successfully: {agent_card.name}")

        print(f"DEBUG: Creating httpx client")
        client = httpx.AsyncClient()
        
        print(f"DEBUG: Creating configuration stores")
        config_store = InMemoryPushNotificationConfigStore()
        
        print(f"DEBUG: Getting agent instance")
        agent_instance = get_agent(agent_card)
        print(f"DEBUG: Agent instance created successfully")
        
        print(f"DEBUG: Creating request handler")
        request_handler = DefaultRequestHandler(
            agent_executor=GenericAgentExecutor(agent=agent_instance),
            task_store=InMemoryTaskStore(),
            queue_manager=InMemoryQueueManager(),
            push_config_store=config_store,
            push_sender=BasePushNotificationSender(client, config_store),
        )
        print(f"DEBUG: Request handler created successfully")

        print(f"DEBUG: Creating A2A server application")
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )
        print(f"DEBUG: A2A server application created successfully")

        logger.info(f'Starting server on {host}:{port}')
        print(f"DEBUG: Starting uvicorn server on {host}:{port}")

        uvicorn.run(server.build(), host=host, port=port)
        print(f"DEBUG: Server started successfully")
    except FileNotFoundError:
        logger.error(f"Error: File '{agent_card}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Error: File '{agent_card}' contains invalid JSON.")
        sys.exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        print(f"DEBUG: Server startup failed with error: {e}")
        print(f"DEBUG: Error type: {type(e)}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == '__main__':
    main()
