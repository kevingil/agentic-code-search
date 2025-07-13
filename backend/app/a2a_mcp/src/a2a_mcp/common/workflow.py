import json
import logging
import uuid

from collections.abc import AsyncIterable
from enum import Enum
from uuid import uuid4

import httpx
import networkx as nx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendStreamingMessageRequest,
    SendStreamingMessageSuccessResponse,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from .utils import get_mcp_server_config
from ..mcp import client


logger = logging.getLogger(__name__)


class Status(Enum):
    """Represents the status of a workflow and its associated node."""

    READY = 'READY'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    PAUSED = 'PAUSED'
    INITIALIZED = 'INITIALIZED'


class WorkflowNode:
    """Represents a single node in a workflow graph.

    Each node encapsulates a specific task to be executed, such as finding an
    agent or invoking an agent's capabilities. It manages its own state
    (e.g., READY, RUNNING, COMPLETED, PAUSED) and can execute its assigned task.

    """

    def __init__(
        self,
        task: str,
        node_key: str | None = None,
        node_label: str | None = None,
    ):
        self.id = str(uuid.uuid4())
        self.node_key = node_key
        self.node_label = node_label
        self.task = task
        self.results = None
        self.state = Status.READY
        self.attributes = {}

    async def get_planner_resource(self) -> AgentCard | None:
        logger.info(f'Getting resource for node {self.id}')
        print(f"DEBUG: Starting get_planner_resource for node {self.id}")
        
        try:
            config = get_mcp_server_config()
            print(f"DEBUG: Got config: {config}")
            
            print(f"DEBUG: About to create session with init_session")
            async with client.init_session(
                config.host, config.port, config.transport
            ) as session:
                print(f"DEBUG: Session created successfully, about to find_resource")
                response = await client.find_resource(
                    session, 'resource://agent_cards/planner_agent'
                )
                print(f"DEBUG: Got response from find_resource")
                data = json.loads(response.contents[0].text)
                print(f"DEBUG: Parsed JSON data")
                result = AgentCard(**data['agent_card'][0])
                print(f"DEBUG: Created AgentCard successfully: {result.name}")
                print(f"DEBUG: Agent card url: {result.url}")
                print(f"DEBUG: Agent card capabilities: {result.capabilities}")
                return result
        except Exception as e:
            print(f"DEBUG: Exception in get_planner_resource: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            raise

    async def find_agent_for_task(self) -> AgentCard | None:
        logger.info(f'Find agent for task - {self.task}')
        print(f"DEBUG: Starting find_agent_for_task for task {self.task}")
        
        # Check if this node has specific agent type attributes and map accordingly
        agent_type = getattr(self, 'agent_type', None)
        if hasattr(self, 'attributes') and self.attributes and 'agent_type' in self.attributes:
            agent_type = self.attributes['agent_type']
        
        print(f"DEBUG: Looking for agent with type: {agent_type}")
        
        # Create a more specific query that includes the agent type if available
        query_text = self.task
        if agent_type:
            query_text = f"Agent type: {agent_type}. Task: {self.task}"
        
        try:
            config = get_mcp_server_config()
            print(f"DEBUG: Got config for find_agent: {config}")
            
            print(f"DEBUG: About to create session for find_agent with query: {query_text}")
            async with client.init_session(
                config.host, config.port, config.transport
            ) as session:
                print(f"DEBUG: Session created for find_agent, calling find_agent")
                result = await client.find_agent(session, query_text)
                print(f"DEBUG: Got result from find_agent")
                
                # Debug the result structure
                print(f"DEBUG: Result type: {type(result)}")
                print(f"DEBUG: Result attributes: {dir(result)}")
                
                if hasattr(result, 'content') and result.content:
                    print(f"DEBUG: Result content length: {len(result.content)}")
                    if len(result.content) > 0:
                        print(f"DEBUG: First content item: {result.content[0]}")
                        print(f"DEBUG: First content text: '{result.content[0].text}'")
                        print(f"DEBUG: First content text length: {len(result.content[0].text)}")
                        
                        if result.content[0].text.strip():
                            try:
                                agent_card_json = json.loads(result.content[0].text)
                                print(f"DEBUG: Parsed JSON for find_agent successfully")
                                
                                # Check if the response is an error
                                if isinstance(agent_card_json, dict) and 'error' in agent_card_json:
                                    error_msg = agent_card_json['error']
                                    print(f"DEBUG: Error response from find_agent: {error_msg}")
                                    raise ValueError(f"MCP server error: {error_msg}")
                                
                                logger.debug(f'Found agent {agent_card_json} for task {self.task}')
                                agent_card = AgentCard(**agent_card_json)
                                print(f"DEBUG: Created AgentCard for find_agent successfully: {agent_card.name}")
                                print(f"DEBUG: Agent card url: {agent_card.url}")
                                print(f"DEBUG: Agent card capabilities: {agent_card.capabilities}")
                                return agent_card
                            except json.JSONDecodeError as json_error:
                                print(f"DEBUG: JSON decode error: {json_error}")
                                print(f"DEBUG: Raw content: '{result.content[0].text}'")
                                raise
                            except TypeError as type_error:
                                print(f"DEBUG: Type error creating AgentCard: {type_error}")
                                print(f"DEBUG: Agent card JSON: {agent_card_json}")
                                raise
                        else:
                            print(f"DEBUG: Content text is empty or whitespace only")
                            raise ValueError("Empty response from find_agent tool")
                    else:
                        print(f"DEBUG: No content items in result")
                        raise ValueError("No content in find_agent result")
                else:
                    print(f"DEBUG: No content attribute in result")
                    raise ValueError("No content attribute in find_agent result")
                    
        except Exception as e:
            print(f"DEBUG: Exception in find_agent_for_task: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            raise

    async def run_node(
        self,
        query: str,
        task_id: str,
        context_id: str,
    ) -> AsyncIterable[dict[str, any]]:
        logger.info(f'Executing node {self.id}')
        print(f"DEBUG: Starting run_node for {self.id}, node_key: {self.node_key}")
        
        agent_card = None
        try:
            if self.node_key == 'planner':
                print(f"DEBUG: Getting planner resource")
                agent_card = await self.get_planner_resource()
                print(f"DEBUG: Got planner resource successfully")
            else:
                print(f"DEBUG: Finding agent for task")
                agent_card = await self.find_agent_for_task()
                print(f"DEBUG: Found agent for task successfully")
        except Exception as e:
            print(f"DEBUG: Error getting agent card: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            raise
            
        print(f"DEBUG: About to create httpx client and A2AClient")
        print(f"DEBUG: Agent card details - Name: {agent_card.name}, URL: {agent_card.url}")
        async with httpx.AsyncClient() as httpx_client:
            print(f"DEBUG: Created httpx client, creating A2AClient")
            print(f"DEBUG: Trying to connect to: {agent_card.url}")
            client = A2AClient(httpx_client, agent_card)
            print(f"DEBUG: Created A2AClient successfully")

            payload: dict[str, any] = {
                'message': {
                    'role': 'user',
                    'parts': [{'kind': 'text', 'text': query}],
                    'messageId': uuid4().hex,
                    'taskId': task_id,
                    'contextId': context_id,
                },
            }
            print(f"DEBUG: Created payload, creating request")
            request = SendStreamingMessageRequest(
                id=str(uuid4()), params=MessageSendParams(**payload)
            )
            print(f"DEBUG: Created request, starting stream")
            response_stream = client.send_message_streaming(request)
            print(f"DEBUG: Got response stream, starting iteration")
            async for chunk in response_stream:
                print(f"DEBUG: Got chunk in response stream")
                # Save the artifact as a result of the node
                if isinstance(
                    chunk.root, SendStreamingMessageSuccessResponse
                ) and (isinstance(chunk.root.result, TaskArtifactUpdateEvent)):
                    artifact = chunk.root.result.artifact
                    self.results = artifact
                yield chunk


class WorkflowGraph:
    """Represents a graph of workflow nodes."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes = {}
        self.latest_node = None
        self.node_type = None
        self.state = Status.INITIALIZED
        self.paused_node_id = None

    def add_node(self, node) -> None:
        logger.info(f'Adding node {node.id}')
        self.graph.add_node(node.id, query=node.task)
        self.nodes[node.id] = node
        self.latest_node = node.id

    def add_edge(self, from_node_id: str, to_node_id: str) -> None:
        if from_node_id not in self.nodes or to_node_id not in self.nodes:
            raise ValueError('Invalid node IDs')

        self.graph.add_edge(from_node_id, to_node_id)

    async def run_workflow(
        self, start_node_id: str = None
    ) -> AsyncIterable[dict[str, any]]:
        logger.info('Executing workflow graph')
        if not start_node_id or start_node_id not in self.nodes:
            start_nodes = [n for n, d in self.graph.in_degree() if d == 0]
        else:
            start_nodes = [self.nodes[start_node_id].id]

        applicable_graph = set()

        for node_id in start_nodes:
            applicable_graph.add(node_id)
            applicable_graph.update(nx.descendants(self.graph, node_id))

        complete_graph = list(nx.topological_sort(self.graph))
        sub_graph = [n for n in complete_graph if n in applicable_graph]
        logger.info(f'Sub graph {sub_graph} size {len(sub_graph)}')
        self.state = Status.RUNNING
        # Alternative is to loop over all nodes, but we only need the connected nodes.
        for node_id in sub_graph:
            node = self.nodes[node_id]
            node.state = Status.RUNNING
            query = self.graph.nodes[node_id].get('query')
            task_id = self.graph.nodes[node_id].get('task_id')
            context_id = self.graph.nodes[node_id].get('context_id')
            async for chunk in node.run_node(query, task_id, context_id):
                # When the workflow node is paused, do not yeild any chunks
                # but, let the loop complete.
                if node.state != Status.PAUSED:
                    if isinstance(
                        chunk.root, SendStreamingMessageSuccessResponse
                    ) and (
                        isinstance(chunk.root.result, TaskStatusUpdateEvent)
                    ):
                        task_status_event = chunk.root.result
                        context_id = task_status_event.contextId
                        if (
                            task_status_event.status.state
                            == TaskState.input_required
                            and context_id
                        ):
                            node.state = Status.PAUSED
                            self.state = Status.PAUSED
                            self.paused_node_id = node.id
                    yield chunk
            if self.state == Status.PAUSED:
                break
            if node.state == Status.RUNNING:
                node.state = Status.COMPLETED
        if self.state == Status.RUNNING:
            self.state = Status.COMPLETED

    def set_node_attribute(self, node_id, attribute, value):
        nx.set_node_attributes(self.graph, {node_id: value}, attribute)
        # Also set on the node object itself
        if node_id in self.nodes:
            node_obj = self.nodes[node_id]
            node_obj.attributes[attribute] = value

    def set_node_attributes(self, node_id, attr_val):
        nx.set_node_attributes(self.graph, {node_id: attr_val})
        # Also set on the node object itself
        if node_id in self.nodes:
            node_obj = self.nodes[node_id]
            node_obj.attributes.update(attr_val)

    def is_empty(self) -> bool:
        return self.graph.number_of_nodes() == 0
