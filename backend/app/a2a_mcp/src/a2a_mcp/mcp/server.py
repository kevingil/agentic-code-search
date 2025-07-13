# type: ignore
import json
import os
import sqlite3
import traceback
import uuid
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import google.generativeai as genai
import numpy as np
import pandas as pd
import requests
from ..mcp_config import mcp_settings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.logging import get_logger
from .db_connection import VectorSearchService
import weave

logger = get_logger(__name__)
# Calculate the path to agent_cards directory relative to this file
AGENT_CARDS_DIR = Path(__file__).parent.parent.parent.parent / "agent_cards"
MODEL = "models/embedding-001"
# Use the same embedding model as the main app for consistency
VECTOR_EMBEDDING_MODEL = "models/text-embedding-004"
SQLLITE_DB = Path(__file__).parent.parent.parent.parent.parent.parent / "code_search.db"
ALLOWED_EXTENSIONS = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rb"}


def init_api_key():
    """Initialize the API key for Google Generative AI."""
    if not mcp_settings.GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is not set")
        raise ValueError("GOOGLE_API_KEY is not set")

    genai.configure(api_key=mcp_settings.GOOGLE_API_KEY)


@weave.op()
def generate_embeddings(text):
    """Generates embeddings for the given text using Google Generative AI.

    Args:
        text: The input string for which to generate embeddings.

    Returns:
        A list of embeddings representing the input text.
    """
    return genai.embed_content(
        model=MODEL,
        content=text,
        task_type="retrieval_document",
    )["embedding"]


def load_agent_cards():
    """Loads agent card data from JSON files within a specified directory.

    Returns:
        A list containing JSON data from an agent card file found in the specified directory.
        Returns an empty list if the directory is empty, contains no '.json' files,
        or if all '.json' files encounter errors during processing.
    """
    card_uris = []
    agent_cards = []
    dir_path = Path(AGENT_CARDS_DIR)
    if not dir_path.is_dir():
        logger.error(
            f"Agent cards directory not found or is not a directory: {AGENT_CARDS_DIR}"
        )
        return card_uris, agent_cards

    logger.info(f"Loading agent cards from card repo: {AGENT_CARDS_DIR}")

    for filename in os.listdir(AGENT_CARDS_DIR):
        if filename.lower().endswith(".json"):
            file_path = dir_path / filename

            if file_path.is_file():
                logger.info(f"Reading file: {filename}")
                try:
                    with file_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                        logger.debug(f"Loaded agent card from {filename}: {type(data)}")
                        logger.debug(f"Agent card data: {data}")
                        card_uris.append(
                            f"resource://agent_cards/{Path(filename).stem}"
                        )
                        agent_cards.append(data)
                except json.JSONDecodeError as jde:
                    logger.error(f"JSON Decoder Error {jde}")
                except OSError as e:
                    logger.error(f"Error reading file {filename}: {e}.")
                except Exception as e:
                    logger.error(
                        f"An unexpected error occurred processing {filename}: {e}",
                        exc_info=True,
                    )
    logger.info(f"Finished loading agent cards. Found {len(agent_cards)} cards.")
    return card_uris, agent_cards


def build_agent_card_embeddings() -> pd.DataFrame:
    """Loads agent cards, generates embeddings for them, and returns a DataFrame.

    Returns:
        pd.DataFrame: A Pandas DataFrame containing the original
        'agent_card' data and their corresponding 'Embeddings'. Returns an empty
        DataFrame if no agent cards were loaded initially or if an exception occurred
        during the embedding generation process.
    """
    card_uris, agent_cards = load_agent_cards()
    logger.info("Generating Embeddings for agent cards")
    try:
        if agent_cards:
            df = pd.DataFrame({"card_uri": card_uris, "agent_card": agent_cards})
            df["card_embeddings"] = df.apply(
                lambda row: generate_embeddings(json.dumps(row["agent_card"])),
                axis=1,
            )
            logger.info("Done generating embeddings for agent cards")
            return df
        else:
            logger.warning("No agent cards loaded, returning empty DataFrame")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"An unexpected error occurred : {e}.", exc_info=True)
        return pd.DataFrame()


def serve(host, port, transport):  # noqa: PLR0915
    """Initializes and runs the Agent Cards MCP server.

    Args:
        host: The hostname or IP address to bind the server to.
        port: The port number to bind the server to.
        transport: The transport mechanism for the MCP server (e.g., 'stdio', 'sse').

    Raises:
        ValueError: If the 'GOOGLE_API_KEY' environment variable is not set.
    """
    init_api_key()
    logger.info("Starting Agent Cards MCP Server")
    mcp = FastMCP("agent-cards", host=host, port=port)

    df = build_agent_card_embeddings()
    
    # Initialize vector search service for code embeddings (if database is configured)
    vector_search_service = None
    try:
        vector_search_service = VectorSearchService()
        logger.info("Vector search service initialized successfully")
    except RuntimeError as e:
        logger.warning(f"Vector search service not available: {e}")
        vector_search_service = None

    @mcp.tool(
        name="find_agent",
        description="Finds the most relevant agent card based on a natural language query string.",
    )
    def find_agent(query: str) -> str:
        """Finds the most relevant agent card based on a query string.

        This function takes a user query, typically a natural language question or a task generated by an agent,
        generates its embedding, and compares it against the
        pre-computed embeddings of the loaded agent cards. It uses the dot
        product to measure similarity and identifies the agent card with the
        highest similarity score.

        Args:
            query: The natural language query string used to search for a
                   relevant agent.

        Returns:
            The json representing the agent card deemed most relevant
            to the input query based on embedding similarity.
        """
        logger.info(f"find_agent called with query: {query}")

        try:
            if df is None or df.empty:
                logger.error("No agent cards loaded")
                return json.dumps({"error": "No agent cards available"})

            query_embedding = genai.embed_content(
                model=MODEL, content=query, task_type="retrieval_query"
            )
            dot_products = np.dot(
                np.stack(df["card_embeddings"]), query_embedding["embedding"]
            )
            best_match_index = np.argmax(dot_products)
            logger.debug(
                f"Found best match at index {best_match_index} with score {dot_products[best_match_index]}"
            )

            # Return the agent card as a JSON string
            agent_card = df.iloc[best_match_index]["agent_card"]
            logger.debug(f"Agent card type: {type(agent_card)}")
            logger.debug(f"Agent card content: {agent_card}")

            # Ensure we return a proper JSON string with robust serialization
            try:
                if isinstance(agent_card, dict):
                    # Use a custom JSON encoder that handles non-serializable objects
                    json_result = json.dumps(
                        agent_card, default=str, ensure_ascii=False
                    )
                    logger.debug(f"JSON result: {json_result}")
                    return json_result
                elif isinstance(agent_card, str):
                    # If it's already a string, check if it's valid JSON
                    try:
                        json.loads(agent_card)  # Validate it's valid JSON
                        return agent_card
                    except json.JSONDecodeError:
                        # If not valid JSON, wrap it
                        return json.dumps({"content": agent_card}, default=str)
                else:
                    # For other types, convert to string and wrap
                    return json.dumps({"content": str(agent_card)}, default=str)
            except Exception as serialize_error:
                logger.error(f"JSON serialization error: {serialize_error}")
                return json.dumps(
                    {"error": f"Serialization failed: {str(serialize_error)}"},
                    default=str,
                )
        except Exception as e:
            logger.error(f"Error in find_agent: {e}")
            return json.dumps({"error": f"Failed to find agent: {str(e)}"})

    @mcp.tool()
    def semantic_code_search(
        query: str, file_pattern: str = "*", language: str = "python"
    ):
        """Perform semantic code search across the codebase."""
        logger.info(
            f"Semantic code search: {query} in {file_pattern} files (language: {language})"
        )

        # Return dummy semantic search results
        dummy_search_results = [
            {
                "file_path": "backend/app/api/routes/agents.py",
                "line_number": 25,
                "code_snippet": "async def query_agent(request: AgentQueryRequest, current_user: User = Depends(get_current_user)):",
                "match_type": "semantic",
                "confidence_score": 0.95,
                "context": "FastAPI endpoint for querying agents with authentication",
                "function_name": "query_agent",
                "class_name": None,
                "docstring": "Query an agent with a specific request",
            },
            {
                "file_path": "backend/app/services/agent_service.py",
                "line_number": 67,
                "code_snippet": "async def query_agent(self, agent_type: str, query: str, context_id: str, task_id: str):",
                "match_type": "semantic",
                "confidence_score": 0.92,
                "context": "Service layer method for agent queries with streaming support",
                "function_name": "query_agent",
                "class_name": "AgentService",
                "docstring": "Query an agent and return streaming responses",
            },
            {
                "file_path": "backend/app/a2a_mcp/src/a2a_mcp/agents/orchestrator_agent.py",
                "line_number": 156,
                "code_snippet": "async def stream(self, query, context_id, task_id) -> AsyncIterable[dict[str, any]]:",
                "match_type": "semantic",
                "confidence_score": 0.88,
                "context": "Orchestrator agent streaming method for handling complex queries",
                "function_name": "stream",
                "class_name": "OrchestratorAgent",
                "docstring": "Execute and stream response",
            },
        ]

        # Filter results based on query content
        if "authentication" in query.lower() or "auth" in query.lower():
            auth_results = [
                {
                    "file_path": "backend/app/core/security.py",
                    "line_number": 45,
                    "code_snippet": "def create_access_token(subject: str, expires_delta: timedelta = None):",
                    "match_type": "semantic",
                    "confidence_score": 0.94,
                    "context": "JWT token creation for authentication",
                    "function_name": "create_access_token",
                    "class_name": None,
                    "docstring": "Create access token for authentication",
                },
                {
                    "file_path": "backend/app/api/deps.py",
                    "line_number": 23,
                    "code_snippet": "def get_current_user(session: Session = Depends(get_session), token: str = Depends(oauth2_scheme)):",
                    "match_type": "semantic",
                    "confidence_score": 0.91,
                    "context": "Dependency for getting current authenticated user",
                    "function_name": "get_current_user",
                    "class_name": None,
                    "docstring": "Get current authenticated user from token",
                },
            ]
            return {"search_results": auth_results}

        return {"search_results": dummy_search_results}

    @mcp.tool()
    def analyze_code_quality(file_path: str, analysis_type: str = "comprehensive"):
        """Analyze code quality for a specific file or pattern."""
        logger.info(f"Code quality analysis: {file_path} (type: {analysis_type})")

        # Return dummy code analysis results
        dummy_analysis_results = {
            "file_path": file_path,
            "analysis_type": analysis_type,
            "issues": [
                {
                    "line_number": 45,
                    "severity": "medium",
                    "description": "Function has too many parameters (6/5)",
                    "suggestion": "Consider using a configuration object or breaking the function into smaller parts",
                    "rule": "complexity/max-params",
                },
                {
                    "line_number": 78,
                    "severity": "low",
                    "description": "Missing type annotation for return value",
                    "suggestion": "Add return type annotation: -> Dict[str, Any]",
                    "rule": "type-hints/missing-return-type",
                },
                {
                    "line_number": 112,
                    "severity": "high",
                    "description": "Potential SQL injection vulnerability",
                    "suggestion": "Use parameterized queries or ORM methods",
                    "rule": "security/sql-injection",
                },
            ],
            "metrics": {
                "complexity": 7.2,
                "maintainability": 8.5,
                "test_coverage": 85.0,
                "lines_of_code": 156,
                "cyclomatic_complexity": 12,
                "technical_debt_ratio": 0.08,
            },
            "suggestions": [
                "Consider breaking down large functions into smaller, more focused functions",
                "Add comprehensive docstrings to all public methods",
                "Implement error handling for edge cases",
                "Add unit tests for uncovered code paths",
            ],
        }

        # Customize results based on analysis type
        if analysis_type == "security":
            dummy_analysis_results["issues"] = [
                issue
                for issue in dummy_analysis_results["issues"]
                if issue["severity"] == "high" or "security" in issue["rule"]
            ]
        elif analysis_type == "performance":
            dummy_analysis_results["issues"] = [
                {
                    "line_number": 34,
                    "severity": "medium",
                    "description": "Inefficient database query in loop",
                    "suggestion": "Use bulk operations or optimize with joins",
                    "rule": "performance/n-plus-one-query",
                }
            ]

        return dummy_analysis_results

    @mcp.tool()
    def generate_documentation(
        file_path: str, doc_type: str = "docstrings", style: str = "google"
    ):
        """Generate documentation for code files."""
        logger.info(
            f"Generate documentation: {file_path} (type: {doc_type}, style: {style})"
        )

        # Return dummy documentation results
        dummy_doc_results = {
            "file_path": file_path,
            "documentation_type": doc_type,
            "style": style,
            "generated_docs": {
                "module_docstring": f'"""{file_path.split("/")[-1].replace(".py", "")} module.\n\nThis module provides functionality for code search and analysis.\n\nTypical usage example:\n\n    from {file_path.split("/")[-1].replace(".py", "")} import main_function\n    result = main_function()\n"""',
                "function_docstrings": [
                    {
                        "function_name": "query_agent",
                        "docstring": '"""Query an agent with a specific request.\n\nArgs:\n    request: AgentQueryRequest containing query and context information\n    current_user: User object for authentication\n\nReturns:\n    AgentQueryResponse: Response containing agent results\n\nRaises:\n    HTTPException: If query validation fails or agent is unavailable\n"""',
                    },
                    {
                        "function_name": "get_agents_status",
                        "docstring": '"""Get status of all available agents.\n\nReturns:\n    List[AgentStatusResponse]: List of agent status information\n\nRaises:\n    HTTPException: If unable to retrieve agent status\n"""',
                    },
                ],
                "class_docstrings": [
                    {
                        "class_name": "AgentQueryRequest",
                        "docstring": '"""Request model for agent queries.\n\nAttributes:\n    query: The search query string\n    context_id: Unique identifier for the session context\n    agent_type: Type of agent to query (orchestrator, code_search, etc.)\n"""',
                    }
                ],
            },
            "existing_docs": {
                "coverage_score": 65.0,
                "missing_docstrings": ["helper_function", "internal_method"],
                "outdated_docstrings": ["legacy_function"],
            },
            "suggestions": [
                "Add comprehensive module-level docstring",
                "Include type hints in all function signatures",
                "Add examples in docstrings for complex functions",
                "Document exception handling patterns",
            ],
        }

        # Customize based on documentation type
        if doc_type == "api_docs":
            dummy_doc_results["generated_docs"]["api_spec"] = {
                "openapi_version": "3.0.0",
                "info": {"title": "Code Search API", "version": "1.0.0"},
                "paths": {
                    "/agents/query": {
                        "post": {
                            "summary": "Query an agent",
                            "parameters": ["request", "current_user"],
                            "responses": {
                                "200": {"description": "Successful response"}
                            },
                        }
                    }
                },
            }

        return dummy_doc_results

    @mcp.tool()
    def search_code_patterns(
        pattern: str, file_extensions: list = None, exclude_dirs: list = None
    ):
        """Search for specific code patterns using regex or AST analysis."""
        logger.info(f"Search code patterns: {pattern}")

        if file_extensions is None:
            file_extensions = [".py", ".js", ".ts", ".java"]
        if exclude_dirs is None:
            exclude_dirs = ["node_modules", "__pycache__", ".git"]

        # Return dummy pattern search results
        dummy_pattern_results = {
            "pattern": pattern,
            "file_extensions": file_extensions,
            "exclude_dirs": exclude_dirs,
            "matches": [
                {
                    "file_path": "backend/app/api/routes/agents.py",
                    "line_number": 15,
                    "match": "from fastapi import APIRouter, HTTPException, Depends",
                    "context": "Import statement for FastAPI dependencies",
                    "pattern_type": "import",
                },
                {
                    "file_path": "backend/app/services/agent_service.py",
                    "line_number": 8,
                    "match": "from typing import Any, Dict, List, Optional, AsyncIterator",
                    "context": "Type hint imports",
                    "pattern_type": "import",
                },
                {
                    "file_path": "backend/app/core/security.py",
                    "line_number": 12,
                    "match": "from datetime import datetime, timedelta",
                    "context": "DateTime utilities import",
                    "pattern_type": "import",
                },
            ],
            "summary": {
                "total_matches": 3,
                "files_searched": 45,
                "pattern_type": "regex",
                "search_time_ms": 234,
            },
        }

        # Customize based on pattern type
        if "async def" in pattern:
            dummy_pattern_results["matches"] = [
                {
                    "file_path": "backend/app/api/routes/agents.py",
                    "line_number": 25,
                    "match": "async def query_agent(request: AgentQueryRequest, current_user: User = Depends(get_current_user)):",
                    "context": "Async FastAPI endpoint",
                    "pattern_type": "function_definition",
                },
                {
                    "file_path": "backend/app/services/agent_service.py",
                    "line_number": 67,
                    "match": "async def query_agent(self, agent_type: str, query: str, context_id: str, task_id: str):",
                    "context": "Async service method",
                    "pattern_type": "function_definition",
                },
            ]

        return dummy_pattern_results

    @mcp.tool()
    def query_code_database(query: str) -> dict:
        """Query the code analysis database with SQL-like syntax.

        This tool provides access to indexed code information including:
        - Functions and their signatures
        - Classes and their methods
        - Import dependencies
        - Code metrics and analysis results

        Args:
            query: SQL-like query string to execute against the code database

        Returns:
            Dictionary containing query results
        """
        logger.info(f"Query code database: {query}")

        # Parse the query to determine what type of data to return
        query_lower = query.lower()

        if "functions" in query_lower:
            # Return dummy function data
            dummy_functions = [
                {
                    "id": 1,
                    "name": "query_agent",
                    "file_path": "backend/app/api/routes/agents.py",
                    "line_number": 25,
                    "signature": "async def query_agent(request: AgentQueryRequest, current_user: User = Depends(get_current_user))",
                    "return_type": "AgentQueryResponse",
                    "complexity": 5,
                    "is_async": True,
                    "is_public": True,
                },
                {
                    "id": 2,
                    "name": "get_agents_status",
                    "file_path": "backend/app/api/routes/agents.py",
                    "line_number": 45,
                    "signature": "async def get_agents_status(current_user: User = Depends(get_current_user))",
                    "return_type": "List[AgentStatusResponse]",
                    "complexity": 3,
                    "is_async": True,
                    "is_public": True,
                },
            ]

            # Filter based on query parameters
            if "async" in query_lower:
                result_functions = [f for f in dummy_functions if f["is_async"]]
            elif "public" in query_lower:
                result_functions = [f for f in dummy_functions if f["is_public"]]
            else:
                result_functions = dummy_functions

            return {"results": result_functions}

        elif "classes" in query_lower:
            # Return dummy class data
            dummy_classes = [
                {
                    "id": 1,
                    "name": "AgentService",
                    "file_path": "backend/app/services/agent_service.py",
                    "line_number": 15,
                    "methods": [
                        "query_agent",
                        "get_agent_status",
                        "clear_agent_context",
                    ],
                    "is_abstract": False,
                    "inheritance": ["object"],
                },
                {
                    "id": 2,
                    "name": "OrchestratorAgent",
                    "file_path": "backend/app/a2a_mcp/src/a2a_mcp/agents/orchestrator_agent.py",
                    "line_number": 25,
                    "methods": ["stream", "generate_summary", "clear_state"],
                    "is_abstract": False,
                    "inheritance": ["BaseAgent"],
                },
            ]

            return {"results": dummy_classes}

        elif "imports" in query_lower:
            # Return dummy import data
            dummy_imports = [
                {
                    "id": 1,
                    "module": "fastapi",
                    "imported_items": ["APIRouter", "HTTPException", "Depends"],
                    "file_path": "backend/app/api/routes/agents.py",
                    "line_number": 1,
                    "is_standard_library": False,
                },
                {
                    "id": 2,
                    "module": "typing",
                    "imported_items": ["Any", "Dict", "List", "Optional"],
                    "file_path": "backend/app/services/agent_service.py",
                    "line_number": 5,
                    "is_standard_library": True,
                },
            ]

            return {"results": dummy_imports}

        # Default empty result
        return json.dumps({"results": []})
        return {"results": []}

    @mcp.tool()
    @weave.op()
    def get_embeddings(text: str) -> dict:
        """Generate embeddings using Google Generative AI"""
        return genai.embed_content(
            model=MODEL,
            content=text,
            task_type="retrieval_document",
        )["embedding"]

    @mcp.tool(
        name="vector_search_code",
        description="Search for similar code chunks using natural language queries. Uses vector embeddings to find semantically similar code across all processed repositories."
    )
    def vector_search_code(
        query: str,
        session_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> str:
        """
        Search for similar code chunks using vector embeddings.
        
        Args:
            query: Natural language description of what you're looking for
            session_id: Optional UUID of specific session to search within
            limit: Maximum number of results (default: 10, max: 50)
            similarity_threshold: Minimum similarity score 0-1 (default: 0.7)
            
        Returns:
            JSON string with search results including code snippets and metadata
        """
        logger.info(f"🚨 MCP TOOL CALLED: vector_search_code with query='{query}' session_id={session_id}")
        try:
            # Check if vector search service is available
            if not vector_search_service:
                error_msg = "Vector search not available. Please configure database connection with POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB environment variables."
                logger.error(f"🚨 Vector search service not available: {error_msg}")
                return json.dumps({"error": error_msg})
            
            # Validate inputs
            limit = min(max(1, limit), 50)  # Clamp between 1 and 50
            similarity_threshold = max(0.0, min(1.0, similarity_threshold))  # Clamp between 0 and 1
            
            # Parse session_id if provided
            session_uuid = None
            if session_id:
                try:
                    session_uuid = uuid.UUID(session_id)
                except ValueError:
                    return json.dumps({"error": "Invalid session_id format. Must be a valid UUID."})
            
            # Generate embedding for the query
            query_embedding = genai.embed_content(
                model=VECTOR_EMBEDDING_MODEL,
                content=query,
                output_dimensionality=768
            )
            
            # Perform the search
            try:
                # Try to run in existing event loop context
                results = asyncio.run(
                    vector_search_service.search_similar_code(
                        query_embedding=query_embedding['embedding'],
                        session_id=session_uuid,
                        limit=limit,
                        similarity_threshold=similarity_threshold
                    )
                )
            except RuntimeError:
                # If there's already a loop running, use asyncio.create_task() approach
                import concurrent.futures
                import threading
                
                def run_async():
                    return asyncio.run(
                        vector_search_service.search_similar_code(
                            query_embedding=query_embedding['embedding'],
                            session_id=session_uuid,
                            limit=limit,
                            similarity_threshold=similarity_threshold
                        )
                    )
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    results = future.result()
            
            # Format results
            response = {
                "query": query,
                "total_results": len(results),
                "similarity_threshold": similarity_threshold,
                "results": results
            }
            
            return json.dumps(response, indent=2)
            
        except Exception as e:
            logger.error(f"Error in vector_search_code: {e}")
            return json.dumps({"error": f"Search failed: {str(e)}"})

    @mcp.tool(
        name="list_code_sessions",
        description="List all code search sessions that have processed vector embeddings."
    )
    def list_code_sessions() -> str:
        """
        Get all sessions that have vector embeddings processed.
        
        Returns:
            JSON string with list of sessions and their metadata
        """
        try:
            # Check if vector search service is available
            if not vector_search_service:
                return json.dumps({
                    "error": "Vector search not available. Please configure database connection with POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB environment variables."
                })
            
            try:
                # Try to run in existing event loop context
                sessions = asyncio.run(
                    vector_search_service.get_sessions_with_embeddings()
                )
            except RuntimeError:
                # If there's already a loop running, use thread pool
                import concurrent.futures
                
                def run_async():
                    return asyncio.run(
                        vector_search_service.get_sessions_with_embeddings()
                    )
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    sessions = future.result()
            
            response = {
                "total_sessions": len(sessions),
                "sessions": sessions
            }
            
            return json.dumps(response, indent=2)
            
        except Exception as e:
            logger.error(f"Error in list_code_sessions: {e}")
            return json.dumps({"error": f"Failed to get sessions: {str(e)}"})

    @mcp.tool(
        name="get_session_files",
        description="Get all files and their chunk information for a specific code search session."
    )
    def get_session_files(session_id: str) -> str:
        """
        Get all files and their chunk information for a specific session.
        
        Args:
            session_id: UUID of the session to get files for
            
        Returns:
            JSON string with file information and chunk statistics
        """
        logger.info(f"🚨 MCP TOOL CALLED: get_session_files with session_id={session_id}")
        try:
            # Check if vector search service is available
            if not vector_search_service:
                error_msg = "Vector search not available. Please configure database connection with POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB environment variables."
                logger.error(f"🚨 Vector search service not available: {error_msg}")
                return json.dumps({"error": error_msg})
            
            # Parse session_id
            try:
                session_uuid = uuid.UUID(session_id)
            except ValueError:
                return json.dumps({"error": "Invalid session_id format. Must be a valid UUID."})
            
            try:
                # Try to run in existing event loop context
                files = asyncio.run(
                    vector_search_service.get_session_files(session_uuid)
                )
            except RuntimeError:
                # If there's already a loop running, use thread pool
                import concurrent.futures
                
                def run_async():
                    return asyncio.run(
                        vector_search_service.get_session_files(session_uuid)
                    )
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    files = future.result()
            
            response = {
                "session_id": session_id,
                "total_files": len(files),
                "files": files
            }
            
            logger.info(f"🚨 MCP TOOL SUCCESS: get_session_files returned {len(files)} files for session {session_id}")
            return json.dumps(response, indent=2)
            
        except Exception as e:
            logger.error(f"Error in get_session_files: {e}")
            return json.dumps({"error": f"Failed to get session files: {str(e)}"})

    @mcp.tool(
        name="search_code_by_file_path",
        description="Search for code chunks by file path pattern. Useful for finding specific files or file types."
    )
    def search_code_by_file_path(
        file_path_pattern: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Search for code chunks by file path pattern.
        
        Args:
            file_path_pattern: SQL LIKE pattern for file paths (use % for wildcards)
            session_id: Optional UUID of specific session to search within
            
        Returns:
            JSON string with matching code chunks
        """
        try:
            # Check if vector search service is available
            if not vector_search_service:
                return json.dumps({
                    "error": "Vector search not available. Please configure database connection with POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB environment variables."
                })
            
            # Parse session_id if provided
            session_uuid = None
            if session_id:
                try:
                    session_uuid = uuid.UUID(session_id)
                except ValueError:
                    return json.dumps({"error": "Invalid session_id format. Must be a valid UUID."})
            
            try:
                # Try to run in existing event loop context
                results = asyncio.run(
                    vector_search_service.search_by_file_path(
                        file_path_pattern=file_path_pattern,
                        session_id=session_uuid
                    )
                )
            except RuntimeError:
                # If there's already a loop running, use thread pool
                import concurrent.futures
                
                def run_async():
                    return asyncio.run(
                        vector_search_service.search_by_file_path(
                            file_path_pattern=file_path_pattern,
                            session_id=session_uuid
                        )
                    )
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    results = future.result()
            
            response = {
                "file_path_pattern": file_path_pattern,
                "total_results": len(results),
                "results": results
            }
            
            return json.dumps(response, indent=2)
            
        except Exception as e:
            logger.error(f"Error in search_code_by_file_path: {e}")
            return json.dumps({"error": f"Failed to search by file path: {str(e)}"})

    @mcp.tool(
        name="generate_query_embedding",
        description="Generate an embedding vector for a text query. Useful for understanding how the vector search works."
    )
    @weave.op()
    def generate_query_embedding(text: str) -> str:
        """
        Generate an embedding vector for a text query.
        
        Args:
            text: The text to generate an embedding for
            
        Returns:
            JSON string with the embedding vector and metadata
        """
        try:
            # Generate embedding
            response = genai.embed_content(
                model=VECTOR_EMBEDDING_MODEL,
                content=text,
                output_dimensionality=768
            )
            
            embedding = response['embedding']
            
            result = {
                "text": text,
                "model": VECTOR_EMBEDDING_MODEL,
                "embedding_dimension": len(embedding),
                "embedding": embedding[:10],  # Show first 10 dimensions for brevity
                "embedding_norm": float(np.linalg.norm(embedding))
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error in generate_query_embedding: {e}")
            return json.dumps({"error": f"Failed to generate embedding: {str(e)}"})

    @mcp.resource("resource://agent_cards/list", mime_type="application/json")
    def get_agent_cards() -> dict:
        """Retrieves all loaded agent cards as a json / dictionary for the MCP resource endpoint.

        This function serves as the handler for the MCP resource identified by
        the URI 'resource://agent_cards/list'.

        Returns:
            A json / dictionary structured as {'agent_cards': [...]}, where the value is a
            list containing all the loaded agent card dictionaries. Returns
            {'agent_cards': []} if the data cannot be retrieved.
        """
        resources = {}
        logger.info("Starting read resources")
        resources["agent_cards"] = df["card_uri"].to_list()
        return resources

    @mcp.resource("resource://agent_cards/{card_name}", mime_type="application/json")
    def get_agent_card(card_name: str) -> dict:
        """Retrieves an agent card as a json / dictionary for the MCP resource endpoint.

        This function serves as the handler for the MCP resource identified by
        the URI 'resource://agent_cards/{card_name}'.

        Returns:
            A json / dictionary
        """
        resources = {}
        logger.info(f"Starting read resource resource://agent_cards/{card_name}")
        resources["agent_card"] = (
            df.loc[
                df["card_uri"] == f"resource://agent_cards/{card_name}",
                "agent_card",
            ]
        ).to_list()

        return resources

    logger.info(f"Agent cards MCP Server at {host}:{port} and transport {transport}")
    mcp.run(transport=transport)
