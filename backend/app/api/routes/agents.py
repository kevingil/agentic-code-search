from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import logging
import asyncio
from contextlib import asynccontextmanager

from app.services.agent_service import agent_service
from app.api.deps import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])


# Request/Response Models
class AgentQueryRequest(BaseModel):
    query: str
    context_id: str
    agent_type: str = (
        "orchestrator"  # orchestrator, air_ticketing, hotel_booking, car_rental
    )


class AgentQueryResponse(BaseModel):
    response_type: str
    is_task_complete: bool
    require_user_input: bool
    content: Any


class AgentStatusResponse(BaseModel):
    agent_name: str
    agent_type: str
    status: str
    description: str
    capabilities: List[str]
    is_active: bool


# Endpoints
@router.get("/agents/status", response_model=List[AgentStatusResponse])
async def get_agents_status(
    current_user: User = Depends(get_current_user),
) -> List[AgentStatusResponse]:
    """Get status of all available agents"""
    try:
        agents_status_list = await agent_service.get_all_agents_status()

        return [
            AgentStatusResponse(
                agent_name=status["agent_name"],
                agent_type=status["agent_type"],
                status=status["status"],
                description=status["description"],
                capabilities=status["capabilities"],
                is_active=status["is_active"],
            )
            for status in agents_status_list
        ]
    except Exception as e:
        logger.error(f"Error getting agents status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get agents status")


@router.post("/agents/query", response_model=AgentQueryResponse)
async def query_agent(
    request: AgentQueryRequest,
    current_user: User = Depends(get_current_user),
) -> AgentQueryResponse:
    """Query an agent with a specific request"""
    try:
        if not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        # Generate a task ID for this query
        task_id = f"task_{current_user.id}_{request.context_id}"

        # Execute the query (collect all streaming responses)
        responses = []
        async for chunk in agent_service.query_agent(
            request.agent_type, request.query, request.context_id, task_id
        ):
            responses.append(chunk)

        # Return the last response (typically the final result)
        if responses:
            final_response = responses[-1]
            return AgentQueryResponse(
                response_type=final_response.get("response_type", "text"),
                is_task_complete=final_response.get("is_task_complete", True),
                require_user_input=final_response.get("require_user_input", False),
                content=final_response.get("content", ""),
            )
        else:
            return AgentQueryResponse(
                response_type="text",
                is_task_complete=True,
                require_user_input=False,
                content="No response from agent",
            )

    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying agent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query agent: {str(e)}")


@router.post("/agents/query/stream")
async def query_agent_stream(
    request: AgentQueryRequest,
    current_user: User = Depends(get_current_user),
):
    """Stream agent responses in real-time"""
    try:
        if not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        # Generate a task ID for this query
        task_id = f"task_{current_user.id}_{request.context_id}"

        async def generate_stream():
            try:
                async for chunk in agent_service.query_agent(
                    request.agent_type, request.query, request.context_id, task_id
                ):
                    # Convert chunk to JSON string and yield
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as e:
                logger.error(f"Error in stream generation: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )

    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting up stream: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to setup stream: {str(e)}")


@router.post("/agents/travel/plan")
async def plan_travel(
    request: AgentQueryRequest,
    current_user: User = Depends(get_current_user),
) -> AgentQueryResponse:
    """Plan a travel itinerary using the orchestrator agent"""
    try:
        # Generate a task ID for this query
        task_id = f"task_{current_user.id}_{request.context_id}"

        # Execute the travel planning (collect all streaming responses)
        responses = []
        async for chunk in agent_service.plan_travel(
            request.query, request.context_id, task_id
        ):
            responses.append(chunk)

        # Return the last response (typically the final result)
        if responses:
            final_response = responses[-1]
            return AgentQueryResponse(
                response_type=final_response.get("response_type", "text"),
                is_task_complete=final_response.get("is_task_complete", True),
                require_user_input=final_response.get("require_user_input", False),
                content=final_response.get("content", ""),
            )
        else:
            return AgentQueryResponse(
                response_type="text",
                is_task_complete=True,
                require_user_input=False,
                content="No response from agent",
            )

    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error planning travel: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to plan travel: {str(e)}")


@router.get("/agents/travel/summary/{context_id}")
async def get_travel_summary(
    context_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get a summary of travel planning results for a specific context"""
    try:
        return await agent_service.generate_travel_summary(context_id)

    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting travel summary: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get travel summary: {str(e)}"
        )


@router.delete("/agents/context/{context_id}")
async def clear_agent_context(
    context_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Clear the context/state for a specific session"""
    try:
        return await agent_service.clear_agent_context(context_id)

    except Exception as e:
        logger.error(f"Error clearing context: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to clear context: {str(e)}"
        )
