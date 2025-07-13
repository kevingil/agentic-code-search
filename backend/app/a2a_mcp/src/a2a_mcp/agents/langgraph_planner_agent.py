# type: ignore

import logging
import os

from collections.abc import AsyncIterable
from typing import Any, Literal

from ..common import prompts
from ..common.base_agent import BaseAgent
from ..common.types import TaskList
from ..common.utils import init_api_key
from ..mcp_config import mcp_settings
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field


memory = MemorySaver()
logger = logging.getLogger(__name__)


class ResponseFormat(BaseModel):
    """Respond to the user in this format."""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    question: str = Field(
        description='Input needed from the user to generate the code search plan'
    )
    content: TaskList = Field(
        description='List of tasks when the code search plan is generated'
    )


# Define code search planning instructions
CODE_SEARCH_PLANNER_INSTRUCTIONS = """
You are an expert code search planner.
You take user input and create comprehensive code search plans, breaking requests into actionable tasks.

CORE PRINCIPLE: Be direct and action-oriented. Minimize follow-up questions.

DEFAULT ASSUMPTIONS FOR REPOSITORY SEARCH:
- Search scope: ENTIRE REPOSITORY (always assume full repo unless specified otherwise)
- Language: DETERMINE from repository content during analysis
- Analysis type: COMPREHENSIVE (search + analysis + documentation as appropriate)
- Output format: DETAILED with code snippets and actionable insights

AVAILABLE AGENT TYPES AND THEIR CAPABILITIES:
1. "Code Search Agent" - Semantic code search using vector_search_code, search_code_by_file_path, list_code_sessions tools
2. "Code Analysis Agent" - Code quality analysis using vector_search_code, analyze_code_quality, search_code_patterns tools  
3. "Code Documentation Agent" - Documentation generation using generate_documentation, vector_search_code tools

IMMEDIATE PLANNING APPROACH:
Based on user query, immediately generate tasks using these specific agent names in descriptions:
1. Code Search Tasks - Use "Code Search Agent" for semantic search, pattern matching, function finding
2. Code Analysis Tasks - Use "Code Analysis Agent" for quality analysis, security analysis, language detection  
3. Documentation Tasks - Use "Code Documentation Agent" for generating docs, analyzing existing docs

SMART INFERENCE WITH SPECIFIC AGENTS:
- "what language" query → SINGLE "Code Search Agent" task (NO complex breakdown)
- "find functions" query → SINGLE "Code Search Agent" task with semantic search
- "code quality" query → SINGLE "Code Analysis Agent" task
- "security" query → SINGLE "Code Analysis Agent" task  
- "documentation" query → SINGLE "Code Documentation Agent" task

MINIMAL QUESTIONS STRATEGY:
- For SIMPLE repository questions (language, files, structure): Create SINGLE task only
- For COMPLEX multi-step requests: Create multiple tasks
- Only ask follow-up questions if the user query is extremely vague (single word or unclear intent)
- Default to SINGLE task for straightforward questions

Your output should follow this JSON format exactly:
{
    'original_query': '[USER_QUERY]',
    'code_search_info': {
        'search_scope': 'entire_codebase',
        'language': 'auto_detect',
        'search_type': 'comprehensive',
        'analysis_depth': 'detailed',
        'output_format': 'structured_report'
    },
    'tasks': [
        {
            'id': 1,
            'description': '[SPECIFIC_ACTIONABLE_TASK_DESCRIPTION]',
            'agent_type': 'code_search|code_analysis|code_documentation',
            'status': 'pending'
        }
    ]
}

EXAMPLE PLANNING FOR "what language is used for this repo?":
{
    'original_query': 'what language is used for this repo?',
    'code_search_info': {
        'search_scope': 'entire_codebase',
        'language': 'auto_detect',
        'search_type': 'repository_analysis',
        'analysis_depth': 'immediate',
        'output_format': 'language_breakdown'
    },
    'tasks': [
        {
            'id': 1,
            'description': 'Analyze repository files to identify programming languages and technology stack',
            'agent_type': 'Code Search Agent',
            'status': 'pending'
        }
    ]
}

Generate plans immediately without asking follow-up questions unless absolutely necessary.
"""


class LangraphPlannerAgent(BaseAgent):
    """Planner Agent backed by LangGraph for code search tasks."""

    def __init__(self):
        init_api_key()

        # Set the GOOGLE_API_KEY environment variable for langchain-google-genai
        os.environ['GOOGLE_API_KEY'] = mcp_settings.GOOGLE_API_KEY

        logger.info('Initializing LanggraphPlannerAgent for code search')

        super().__init__(
            agent_name='planner_agent',
            description='Breakdown code search requests into executable tasks',
            content_types=['text', 'text/plain'],
        )

        self.model = ChatGoogleGenerativeAI(
            model='gemini-2.0-flash', temperature=0.0
        )

        self.graph = create_react_agent(
            self.model,
            checkpointer=memory,
            prompt=CODE_SEARCH_PLANNER_INSTRUCTIONS,
            response_format=ResponseFormat,
            tools=[],
        )

    def invoke(self, query, sessionId) -> str:
        config = {'configurable': {'thread_id': sessionId}}
        self.graph.invoke({'messages': [('user', query)]}, config)
        return self.get_agent_response(config)

    async def stream(
        self, query, sessionId, task_id
    ) -> AsyncIterable[dict[str, Any]]:
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': sessionId}}

        logger.info(
            f'Running LanggraphPlannerAgent stream for session {sessionId} {task_id} with input {query}'
        )

        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if isinstance(message, AIMessage):
                yield {
                    'response_type': 'text',
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': message.content,
                }
        yield self.get_agent_response(config)

    def get_agent_response(self, config):
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')
        if structured_response and isinstance(
            structured_response, ResponseFormat
        ):
            if (
                structured_response.status == 'input_required'
                # and structured_response.content.tasks
            ):
                return {
                    'response_type': 'text',
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.question,
                }
            if structured_response.status == 'error':
                return {
                    'response_type': 'text',
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.question,
                }
            if structured_response.status == 'completed':
                return {
                    'response_type': 'data',
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': structured_response.content.model_dump(),
                }
        return {
            'is_task_complete': False,
            'require_user_input': True,
            'content': 'We are unable to process your code search request at the moment. Please try again.',
        }
