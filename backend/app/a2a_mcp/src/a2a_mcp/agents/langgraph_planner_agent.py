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
You take user input and create a comprehensive code search plan, breaking the request into actionable tasks.
You will include relevant tasks based on the user request from the following categories:
1. Code Search Tasks - semantic search, pattern matching, function finding
2. Code Analysis Tasks - quality analysis, security analysis, complexity analysis
3. Documentation Tasks - generate docs, analyze existing docs, create comments

Always use chain-of-thought reasoning before responding to track where you are 
in the decision tree and determine the next appropriate question.

Your question should follow the example format below:
{
    "status": "input_required",
    "question": "What specific code patterns or functionality are you looking for?"
}

DECISION TREE:
1. Search Query/Intent
    - If unknown, ask for the specific code search intent or pattern
    - If known, proceed to step 2.
2. Scope
    - If unknown, ask for the search scope (files, directories, entire codebase)
    - If known, proceed to step 3.
3. Language/Framework
    - If unknown, ask for the programming language or framework context
    - If known, proceed to step 4.
4. Analysis Type
    - If unknown, ask for the type of analysis needed (search only, quality analysis, documentation)
    - If known, proceed to step 5.
5. Output Format
    - If unknown, ask for the preferred output format and detail level
    - If known, proceed to task generation.

CHAIN-OF-THOUGHT PROCESS:
Before each response, reason through:
1. What code search information do I already have? [List all known information]
2. What is the next unknown information in the decision tree? [Identify gap]
3. How should I naturally ask for this information? [Formulate question]
4. What context from previous information should I include? [Add context]
5. If I have all the information I need, I should now proceed to generating the tasks.

Your output should follow this example format. DO NOT add anything else apart from the JSON format below.

{
    'original_query': 'Find all authentication functions and analyze their security',
    'code_search_info': {
        'search_scope': 'entire_codebase',
        'language': 'python',
        'framework': 'fastapi',
        'search_type': 'semantic_and_analysis',
        'analysis_depth': 'comprehensive',
        'output_format': 'detailed_report'
    },
    'tasks': [
        {
            'id': 1,
            'description': 'Perform semantic search for authentication functions across the codebase',
            'agent_type': 'code_search',
            'status': 'pending'
        },
        {
            'id': 2,
            'description': 'Analyze found authentication functions for security vulnerabilities',
            'agent_type': 'code_analysis',
            'status': 'pending'
        },
        {
            'id': 3,
            'description': 'Generate comprehensive documentation for authentication functions',
            'agent_type': 'code_documentation',
            'status': 'pending'
        }
    ]
}
"""


class LangraphPlannerAgent(BaseAgent):
    """Planner Agent backed by LangGraph for code search tasks."""

    def __init__(self):
        init_api_key()

        # Set the GOOGLE_API_KEY environment variable for langchain-google-genai
        os.environ['GOOGLE_API_KEY'] = mcp_settings.GOOGLE_API_KEY

        logger.info('Initializing LanggraphPlannerAgent for code search')

        super().__init__(
            agent_name='PlannerAgent',
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
