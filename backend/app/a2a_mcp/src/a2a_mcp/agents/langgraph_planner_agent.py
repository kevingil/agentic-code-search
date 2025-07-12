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
        description='Input needed from the user to generate the plan'
    )
    content: TaskList = Field(
        description='List of tasks when the plan is generated'
    )


class LangraphPlannerAgent(BaseAgent):
    """Planner Agent backed by LangGraph."""

    def __init__(self):
        print(f"DEBUG: LangraphPlannerAgent.__init__ - calling init_api_key()")
        try:
            init_api_key()
            print(f"DEBUG: LangraphPlannerAgent.__init__ - init_api_key() completed successfully")
        except Exception as e:
            print(f"DEBUG: LangraphPlannerAgent.__init__ - init_api_key() failed: {e}")
            raise

        # Set the GOOGLE_API_KEY environment variable for langchain-google-genai
        print(f"DEBUG: LangraphPlannerAgent.__init__ - setting GOOGLE_API_KEY environment variable")
        print(f"DEBUG: mcp_settings.GOOGLE_API_KEY = '{mcp_settings.GOOGLE_API_KEY}'")
        print(f"DEBUG: len(mcp_settings.GOOGLE_API_KEY) = {len(mcp_settings.GOOGLE_API_KEY)}")
        os.environ['GOOGLE_API_KEY'] = mcp_settings.GOOGLE_API_KEY
        print(f"DEBUG: os.environ['GOOGLE_API_KEY'] = '{os.environ.get('GOOGLE_API_KEY')}'")
        print(f"DEBUG: LangraphPlannerAgent.__init__ - GOOGLE_API_KEY environment variable set")

        logger.info('Initializing LanggraphPlannerAgent')
        print(f"DEBUG: LangraphPlannerAgent.__init__ - calling super().__init__")

        super().__init__(
            agent_name='PlannerAgent',
            description='Breakdown the user request into executable tasks',
            content_types=['text', 'text/plain'],
        )
        print(f"DEBUG: LangraphPlannerAgent.__init__ - super().__init__ completed")

        print(f"DEBUG: LangraphPlannerAgent.__init__ - creating ChatGoogleGenerativeAI model")
        try:
            self.model = ChatGoogleGenerativeAI(
                model='gemini-2.0-flash', temperature=0.0
            )
            print(f"DEBUG: LangraphPlannerAgent.__init__ - ChatGoogleGenerativeAI created successfully")
        except Exception as e:
            print(f"DEBUG: LangraphPlannerAgent.__init__ - ChatGoogleGenerativeAI failed: {e}")
            print(f"DEBUG: Error type: {type(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            raise

        print(f"DEBUG: LangraphPlannerAgent.__init__ - creating react agent graph")
        try:
            self.graph = create_react_agent(
                self.model,
                checkpointer=memory,
                prompt=prompts.PLANNER_COT_INSTRUCTIONS,
                # prompt=prompts.TRIP_PLANNER_INSTRUCTIONS_1,
                response_format=ResponseFormat,
                tools=[],
            )
            print(f"DEBUG: LangraphPlannerAgent.__init__ - react agent graph created successfully")
        except Exception as e:
            print(f"DEBUG: LangraphPlannerAgent.__init__ - react agent graph creation failed: {e}")
            raise
            
        print(f"DEBUG: LangraphPlannerAgent.__init__ - completed successfully")

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
            'content': 'We are unable to process your request at the moment. Please try again.',
        }
