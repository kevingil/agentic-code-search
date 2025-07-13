# type: ignore

import json
import logging
import re
import os

from collections.abc import AsyncIterable
from typing import Any

from ..common.agent_runner import AgentRunner
from ..common.base_agent import BaseAgent
from ..common.utils import get_mcp_server_config, init_api_key
from ..mcp_config import mcp_settings
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseServerParams
from google.genai import types as genai_types


logger = logging.getLogger(__name__)


class CodeSearchAgent(BaseAgent):
    """Code Search Agent backed by ADK."""

    def __init__(self, agent_name: str, description: str, instructions: str):
        init_api_key()

        # Set the GOOGLE_API_KEY environment variable for Google services
        os.environ["GOOGLE_API_KEY"] = mcp_settings.GOOGLE_API_KEY

        super().__init__(
            agent_name=agent_name,
            description=description,
            content_types=["text", "text/plain"],
        )

        logger.info(f"Init {self.agent_name}")

        self.instructions = instructions
        self.agent = None

    async def init_agent(self, session_id: str = None):
        logger.info(f"Initializing {self.agent_name} metadata")
        config = get_mcp_server_config()
        logger.info(f"MCP Server url={config.url}")

        # Get tools from MCP server
        tools = await MCPToolset(
            connection_params=SseServerParams(url=config.url)
        ).get_tools()

        for tool in tools:
            logger.info(f"Loaded tool {tool.name}")

        # Include session context in the instructions
        session_aware_instructions = self.instructions
        if session_id:
            session_aware_instructions = f"""
🚨 MANDATORY SESSION CONTEXT 🚨
Your EXACT session ID is: {session_id}

CRITICAL REQUIREMENTS:
1. IMMEDIATELY use MCP tools with session_id="{session_id}" 
2. For ANY question, start by calling get_session_files(session_id="{session_id}")
3. Use the EXACT session_id "{session_id}" in every tool call
4. Do NOT ask follow-up questions - use tools to get answers

{self.instructions}

🚨 YOU MUST USE THESE TOOLS IMMEDIATELY:
- get_session_files(session_id="{session_id}") 
- vector_search_code(query="search_term", session_id="{session_id}")
- search_code_by_file_path(file_path_pattern="*.py", session_id="{session_id}")

FAILURE TO USE MCP TOOLS = TASK FAILURE
"""

        generate_content_config = genai_types.GenerateContentConfig(temperature=0.0)
        self.agent = Agent(
            name=self.agent_name,
            instruction=session_aware_instructions,
            model="gemini-2.0-flash",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=generate_content_config,
            tools=tools,
        )
        self.runner = AgentRunner()

    async def invoke(self, query, session_id) -> dict:
        logger.info(f"Running {self.agent_name} for session {session_id}")

        raise NotImplementedError("Please use the streaming function")

    async def stream(self, query, context_id, task_id) -> AsyncIterable[dict[str, Any]]:
        logger.info(
            f"Running {self.agent_name} stream for session {context_id} {task_id} - {query}"
        )

        if not query:
            raise ValueError("Query cannot be empty")

        if not self.agent:
            await self.init_agent(session_id=context_id)

        async for chunk in self.runner.run_stream(self.agent, query, context_id):
            logger.info(f"Received chunk {chunk}")
            if isinstance(chunk, dict) and chunk.get("type") == "final_result":
                response = chunk["response"]
                yield self.get_agent_response(response)
            else:
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": f"{self.agent_name}: Processing Request...",
                }

    def format_response(self, chunk):
        patterns = [
            r"```\n(.*?)\n```",
            r"```json\s*(.*?)\s*```",
            r"```tool_outputs\s*(.*?)\s*```",
        ]

        for pattern in patterns:
            match = re.search(pattern, chunk, re.DOTALL)
            if match:
                content = match.group(1)
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return content
        return chunk

    def get_agent_response(self, chunk):
        logger.info(f"Response Type {type(chunk)}")
        data = self.format_response(chunk)
        logger.info(f"Formatted Response {data}")
        try:
            if isinstance(data, dict):
                if "status" in data and data["status"] == "input_required":
                    return {
                        "response_type": "text",
                        "is_task_complete": False,
                        "require_user_input": True,
                        "content": data["question"],
                    }
                return {
                    "response_type": "data",
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": data,
                }

            # Handle string responses
            if isinstance(data, str):
                # Check if it's empty or just whitespace
                if not data.strip():
                    logger.warning("Received empty response, returning default message")
                    return {
                        "response_type": "text",
                        "is_task_complete": True,
                        "require_user_input": False,
                        "content": "Code search task completed successfully.",
                    }

                # Try to parse as JSON
                try:
                    parsed_data = json.loads(data)
                    return {
                        "response_type": "data",
                        "is_task_complete": True,
                        "require_user_input": False,
                        "content": parsed_data,
                    }
                except json.JSONDecodeError as json_e:
                    logger.info(f"Response is not JSON, treating as text: {json_e}")
                    return {
                        "response_type": "text",
                        "is_task_complete": True,
                        "require_user_input": False,
                        "content": data,
                    }

            # Handle other types (fallback)
            return {
                "response_type": "text",
                "is_task_complete": True,
                "require_user_input": False,
                "content": str(data)
                if data is not None
                else "Code search task completed successfully.",
            }
        except Exception as e:
            logger.error(f"Error in get_agent_response: {e}")
            return {
                "response_type": "text",
                "is_task_complete": True,
                "require_user_input": False,
                "content": "Could not complete code search task. Please try again.",
            }
