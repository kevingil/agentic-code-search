import json
import logging
import os
import weave
from collections.abc import AsyncIterable
from a2a.types import (
    SendStreamingMessageSuccessResponse,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from ..common import prompts
from ..common.base_agent import BaseAgent
from ..common.utils import init_api_key
from ..common.workflow import Status, WorkflowGraph, WorkflowNode
from ..mcp_config import mcp_settings
from google import genai


logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """Orchestrator Agent."""

    def __init__(self):
        init_api_key()

        # Set the GOOGLE_API_KEY environment variable for Google services
        os.environ["GOOGLE_API_KEY"] = mcp_settings.GOOGLE_API_KEY

        super().__init__(
            agent_name="orchestrator_agent",
            description="Coordinate complex code search and analysis workflows",
            content_types=["text", "text/plain"],
        )

        self.graph = None
        self.results = []
        self.code_search_context = {}
        self.query_history = []
        self.context_id = None
        
        # No need for separate agent - we'll handle simple questions directly

    @weave.op()
    def is_simple_repository_question(self, query: str) -> bool:
        """
        Detect if this is a simple repository analysis question that can be answered directly
        by a single agent using MCP tools, without complex workflow orchestration.
        """
        # Use LLM to determine if this is a simple repository question
        try:
            client = genai.Client()
            analysis_prompt = f"""
Analyze this user query and determine if it's a simple repository question that can be answered directly using code search tools:

Query: "{query}"

Simple repository questions include:
- Questions about programming languages used
- Questions about file structure or organization  
- Questions about technologies, frameworks, or libraries used
- Questions asking for repository overview or summary
- Questions about specific files or directories
- Questions about code patterns or functions

Complex questions that need workflow orchestration:
- Multi-step analysis requests
- Questions requiring code generation or modification
- Questions requiring complex cross-file analysis
- Questions requiring external API calls or integrations

Respond with just "SIMPLE" or "COMPLEX".
"""
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=analysis_prompt,
                config={"temperature": 0.0}
            )
            
            result = response.text.strip().upper()
            return result == "SIMPLE"
            
        except Exception as e:
            logger.error(f"Error in LLM-based question classification: {e}")
            # Fallback to assuming it's simple if we can't classify
            return True



    async def _route_to_code_search_agent(self, query: str, context_id: str, task_id: str) -> AsyncIterable[dict[str, any]]:
        """
        Route simple repository questions directly to a Code Search Agent that uses MCP tools.
        """
        logger.info(f"Routing to Code Search Agent: {query}")
        
        try:
            # Import here to avoid circular imports
            from .adk_travel_agent import CodeSearchAgent
            
            # Create Code Search Agent with proper configuration
            code_agent = CodeSearchAgent(
                agent_name="code_search_agent",
                description="Code search agent for direct repository analysis",
                instructions=prompts.CODE_SEARCH_INSTRUCTIONS
            )
            
            # Initialize agent with session context
            await code_agent.init_agent(session_id=context_id)
            
            # Stream responses from the Code Search Agent
            async for chunk in code_agent.stream(query, context_id, task_id):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error routing to Code Search Agent: {e}")
            yield {
                'response_type': 'text',
                'is_task_complete': True,
                'require_user_input': False,
                'content': f"Error: Unable to process repository question - {str(e)}"
            }



    @weave.op()
    async def generate_summary(self) -> str:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompts.SUMMARY_COT_INSTRUCTIONS.replace(
                "{code_search_data}", str(self.results)
            ),
            config={"temperature": 0.0},
        )
        return response.text

    @weave.op()
    def answer_user_question(self, question) -> str:
        try:
            client = genai.Client()
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompts.QA_COT_PROMPT.replace(
                    "{CODE_SEARCH_CONTEXT}", str(self.code_search_context)
                )
                .replace("{CONVERSATION_HISTORY}", str(self.query_history))
                .replace("{CODE_QUESTION}", question),
                config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            )
            return response.text
        except Exception as e:
            logger.info(f"Error answering user question: {e}")
        return (
            '{"can_answer": "no", "answer": "Cannot answer based on provided context"}'
        )

    def set_node_attributes(self, node_id, task_id=None, context_id=None, query=None):
        attr_val = {}
        if task_id:
            attr_val["task_id"] = task_id
        if context_id:
            attr_val["context_id"] = context_id
        if query:
            attr_val["query"] = query

        self.graph.set_node_attributes(node_id, attr_val)

    def add_graph_node(
        self,
        task_id,
        context_id,
        query: str,
        node_id: str = None,
        node_key: str = None,
        node_label: str = None,
    ) -> WorkflowNode:
        """Add a node to the graph."""
        node = WorkflowNode(task=query, node_key=node_key, node_label=node_label)
        self.graph.add_node(node)
        if node_id:
            self.graph.add_edge(node_id, node.id)
        self.set_node_attributes(node.id, task_id, context_id, query)
        return node

    def clear_state(self):
        self.graph = None
        self.results.clear()
        self.code_search_context.clear()
        self.query_history.clear()

    async def stream(self, query, context_id, task_id) -> AsyncIterable[dict[str, any]]:
        """Execute and stream response."""
        logger.info(
            f"Running {self.agent_name} stream for session {context_id}, task {task_id} - {query}"
        )
        if not query:
            raise ValueError("Query cannot be empty")
        if self.context_id != context_id:
            # Clear state when the context changes
            self.clear_state()
            self.context_id = context_id

        self.query_history.append(query)
        
        # Check if this is a simple repository question that can be answered directly
        if self.is_simple_repository_question(query):
            logger.info(f"Detected simple repository question, routing to Code Search Agent: {query}")
            
            try:
                # Route directly to Code Search Agent with proper MCP tools access
                async for chunk in self._route_to_code_search_agent(query, context_id, task_id):
                    yield chunk
                return
                
            except Exception as e:
                logger.error(f"Error in direct agent routing: {e}")
                # Fall back to normal workflow orchestration
                logger.info("Falling back to normal workflow orchestration")
                pass
        
        start_node_id = None
        # Graph does not exist, start a new graph with planner node.
        if not self.graph:
            self.graph = WorkflowGraph()
            planner_node = self.add_graph_node(
                task_id=task_id,
                context_id=context_id,
                query=query,
                node_key="planner",
                node_label="Planner",
            )
            start_node_id = planner_node.id
        # Paused state is when the agent might need more information.
        elif self.graph.state == Status.PAUSED:
            start_node_id = self.graph.paused_node_id
            self.set_node_attributes(node_id=start_node_id, query=query)

        # This loop can be avoided if the workflow graph is dynamic or
        # is built from the results of the planner when the planner
        # iself is not a part of the graph.
        # TODO: Make the graph dynamically iterable over edges
        while True:
            # Set attributes on the node so we propagate task and context
            self.set_node_attributes(
                node_id=start_node_id,
                task_id=task_id,
                context_id=context_id,
            )
            # Resume workflow, used when the workflow nodes are updated.
            should_resume_workflow = False
            async for chunk in self.graph.run_workflow(start_node_id=start_node_id):
                if isinstance(chunk.root, SendStreamingMessageSuccessResponse):
                    # The graph node retured TaskStatusUpdateEvent
                    # Check if the node is complete and continue to the next node
                    if isinstance(chunk.root.result, TaskStatusUpdateEvent):
                        task_status_event = chunk.root.result
                        context_id = task_status_event.contextId
                        if (
                            task_status_event.status.state == TaskState.completed
                            and context_id
                        ):
                            ## yeild??
                            continue
                        if task_status_event.status.state == TaskState.input_required:
                            question = task_status_event.status.message.parts[
                                0
                            ].root.text

                            try:
                                answer = json.loads(self.answer_user_question(question))
                                logger.info(f"Agent Answer {answer}")
                                if answer["can_answer"] == "yes":
                                    # Orchestrator can answer on behalf of the user set the query
                                    # Resume workflow from paused state.
                                    query = answer["answer"]
                                    start_node_id = self.graph.paused_node_id
                                    self.set_node_attributes(
                                        node_id=start_node_id, query=query
                                    )
                                    should_resume_workflow = True
                            except Exception:
                                logger.info("Cannot convert answer data")

                    # The graph node retured TaskArtifactUpdateEvent
                    # Store the node and continue.
                    if isinstance(chunk.root.result, TaskArtifactUpdateEvent):
                        artifact = chunk.root.result.artifact
                        self.results.append(artifact)
                        if artifact.name == "PlannerAgent-result":
                            # Planning agent returned data, update graph.
                            artifact_data = artifact.parts[0].root.data
                            if "code_search_info" in artifact_data:
                                self.code_search_context = artifact_data[
                                    "code_search_info"
                                ]
                            logger.info(
                                f"Updating workflow with {len(artifact_data['tasks'])} task nodes"
                            )
                            # Define the edges
                            current_node_id = start_node_id
                            for idx, task_data in enumerate(artifact_data["tasks"]):
                                node = self.add_graph_node(
                                    task_id=task_id,
                                    context_id=context_id,
                                    query=task_data["description"],
                                    node_id=current_node_id,
                                )
                                
                                # Set agent_type attribute if available
                                if "agent_type" in task_data:
                                    self.graph.set_node_attribute(node.id, "agent_type", task_data["agent_type"])
                                
                                current_node_id = node.id
                                # Restart graph from the newly inserted subgraph state
                                # Start from the new node just created.
                                if idx == 0:
                                    should_resume_workflow = True
                                    start_node_id = node.id
                        else:
                            # Not planner but artifacts from other tasks,
                            # continue to the next node in the workflow.
                            # client does not get the artifact,
                            # a summary is shown at the end of the workflow.
                            continue
                # When the workflow needs to be resumed, do not yield partial.
                if not should_resume_workflow:
                    logger.info("No workflow resume detected, yielding chunk")
                    # Extract relevant data from the chunk and yield as a dictionary
                    if isinstance(chunk.root, SendStreamingMessageSuccessResponse):
                        # Convert the response to a JSON-serializable dictionary
                        chunk_data = {
                            "response_type": "text",
                            "is_task_complete": False,
                            "require_user_input": False,
                            "content": "Processing code search request...",
                        }

                        # Try to extract more meaningful content if available
                        if hasattr(chunk.root, "result") and chunk.root.result:
                            result = chunk.root.result
                            if hasattr(result, "status") and result.status:
                                if (
                                    hasattr(result.status, "message")
                                    and result.status.message
                                ):
                                    if (
                                        hasattr(result.status.message, "parts")
                                        and result.status.message.parts
                                    ):
                                        try:
                                            chunk_data["content"] = (
                                                result.status.message.parts[0].root.text
                                            )
                                        except (AttributeError, IndexError):
                                            pass

                        yield chunk_data
                    else:
                        # For other types of chunks, try to convert to dict or use default
                        try:
                            if hasattr(chunk, "model_dump"):
                                yield chunk.model_dump()
                            elif hasattr(chunk, "dict"):
                                yield chunk.dict()
                            else:
                                yield {
                                    "response_type": "text",
                                    "is_task_complete": False,
                                    "require_user_input": False,
                                    "content": str(chunk),
                                }
                        except Exception as e:
                            logger.warning(f"Error converting chunk to dict: {e}")
                            yield {
                                "response_type": "text",
                                "is_task_complete": False,
                                "require_user_input": False,
                                "content": "Processing code search request...",
                            }
            # The graph is complete and no updates, so okay to break from the loop.
            if not should_resume_workflow:
                logger.info(
                    "Workflow iteration complete and no restart requested. Exiting main loop."
                )
                break
            else:
                # Readable logs
                logger.info("Restarting workflow loop.")
        if self.graph.state == Status.COMPLETED:
            # All individual actions complete, now generate the summary
            logger.info(f"Generating summary for {len(self.results)} results")
            summary = await self.generate_summary()
            self.clear_state()
            logger.info(f"Summary: {summary}")
            yield {
                "response_type": "text",
                "is_task_complete": True,
                "require_user_input": False,
                "content": summary,
            }
