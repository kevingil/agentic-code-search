# type:ignore
import asyncio
import json
import os

from contextlib import asynccontextmanager

import click

from app.core.config import settings
from fastmcp.utilities.logging import get_logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ReadResourceResult


logger = get_logger(__name__)

env = {
    "GOOGLE_API_KEY": settings.GOOGLE_API_KEY,
}


@asynccontextmanager
async def init_session(host, port, transport):
    """Initializes and manages an MCP ClientSession based on the specified transport.

    This asynchronous context manager establishes a connection to an MCP server
    using either Server-Sent Events (SSE) or Standard I/O (STDIO) transport.
    It handles the setup and teardown of the connection and yields an active
    `ClientSession` object ready for communication.

    Args:
        host: The hostname or IP address of the MCP server (used for SSE).
        port: The port number of the MCP server (used for SSE).
        transport: The communication transport to use ('sse' or 'stdio').

    Yields:
        ClientSession: An initialized and ready-to-use MCP client session.

    Raises:
        ValueError: If an unsupported transport type is provided (implicitly,
                    as it won't match 'sse' or 'stdio').
        Exception: Other potential exceptions during client initialization or
                   session setup.
    """
    if transport == "sse":
        url = f"http://{host}:{port}/sse"
        async with sse_client(url) as (read_stream, write_stream):
            async with ClientSession(
                read_stream=read_stream, write_stream=write_stream
            ) as session:
                logger.debug("SSE ClientSession created, initializing...")
                await session.initialize()
                logger.info("SSE ClientSession initialized successfully.")
                yield session
    elif transport == "stdio":
        if not settings.GOOGLE_API_KEY:
            logger.error("GOOGLE_API_KEY is not set")
            raise ValueError("GOOGLE_API_KEY is not set")
        stdio_params = StdioServerParameters(
            command="uv",
            args=["run", "a2a-mcp"],
            env=env,
        )
        async with stdio_client(stdio_params) as (read_stream, write_stream):
            async with ClientSession(
                read_stream=read_stream,
                write_stream=write_stream,
            ) as session:
                logger.debug("STDIO ClientSession created, initializing...")
                await session.initialize()
                logger.info("STDIO ClientSession initialized successfully.")
                yield session
    else:
        logger.error(f"Unsupported transport type: {transport}")
        raise ValueError(
            f"Unsupported transport type: {transport}. Must be 'sse' or 'stdio'."
        )


async def find_agent(session: ClientSession, query) -> CallToolResult:
    """Calls the 'find_agent' tool on the connected MCP server.

    Args:
        session: The active ClientSession.
        query: The natural language query to send to the 'find_agent' tool.

    Returns:
        The result of the tool call.
    """
    logger.info(f"Calling 'find_agent' tool with query: '{query[:50]}...'")
    return await session.call_tool(
        name="find_agent",
        arguments={
            "query": query,
        },
    )


async def find_resource(session: ClientSession, resource) -> ReadResourceResult:
    """Reads a resource from the connected MCP server.

    Args:
        session: The active ClientSession.
        resource: The URI of the resource to read (e.g., 'resource://agent_cards/list').

    Returns:
        The result of the resource read operation.
    """
    logger.info(f"Reading resource: {resource}")
    return await session.read_resource(resource)


async def semantic_code_search(
    session: ClientSession,
    query: str,
    file_pattern: str = "*",
    language: str = "python",
) -> CallToolResult:
    """Calls the 'semantic_code_search' tool on the connected MCP server.

    Args:
        session: The active ClientSession.
        query: The search query for semantic code search.
        file_pattern: File pattern to search (default: "*").
        language: Programming language to focus on (default: "python").

    Returns:
        The result of the tool call.
    """
    logger.info(f"Calling 'semantic_code_search' tool with query: '{query}'")
    return await session.call_tool(
        name="semantic_code_search",
        arguments={
            "query": query,
            "file_pattern": file_pattern,
            "language": language,
        },
    )


async def analyze_code_quality(
    session: ClientSession, file_path: str, analysis_type: str = "comprehensive"
) -> CallToolResult:
    """Calls the 'analyze_code_quality' tool on the connected MCP server.

    Args:
        session: The active ClientSession.
        file_path: The file path to analyze.
        analysis_type: Type of analysis to perform (default: "comprehensive").

    Returns:
        The result of the tool call.
    """
    logger.info(f"Calling 'analyze_code_quality' tool for file: '{file_path}'")
    return await session.call_tool(
        name="analyze_code_quality",
        arguments={
            "file_path": file_path,
            "analysis_type": analysis_type,
        },
    )


async def generate_documentation(
    session: ClientSession,
    file_path: str,
    doc_type: str = "docstrings",
    style: str = "google",
) -> CallToolResult:
    """Calls the 'generate_documentation' tool on the connected MCP server.

    Args:
        session: The active ClientSession.
        file_path: The file path to generate documentation for.
        doc_type: Type of documentation to generate (default: "docstrings").
        style: Documentation style to use (default: "google").

    Returns:
        The result of the tool call.
    """
    logger.info(f"Calling 'generate_documentation' tool for file: '{file_path}'")
    return await session.call_tool(
        name="generate_documentation",
        arguments={
            "file_path": file_path,
            "doc_type": doc_type,
            "style": style,
        },
    )


async def search_code_patterns(
    session: ClientSession,
    pattern: str,
    file_extensions: list = None,
    exclude_dirs: list = None,
) -> CallToolResult:
    """Calls the 'search_code_patterns' tool on the connected MCP server.

    Args:
        session: The active ClientSession.
        pattern: The code pattern to search for.
        file_extensions: List of file extensions to include (default: None).
        exclude_dirs: List of directories to exclude (default: None).

    Returns:
        The result of the tool call.
    """
    logger.info(f"Calling 'search_code_patterns' tool with pattern: '{pattern}'")
    return await session.call_tool(
        name="search_code_patterns",
        arguments={
            "pattern": pattern,
            "file_extensions": file_extensions,
            "exclude_dirs": exclude_dirs,
        },
    )


async def query_code_database(session: ClientSession, query: str) -> CallToolResult:
    """Calls the 'query_code_database' tool on the connected MCP server.

    Args:
        session: The active ClientSession.
        query: The SQL-like query to execute against the code database.

    Returns:
        The result of the tool call.
    """
    logger.info(f"Calling 'query_code_database' tool with query: '{query}'")
    return await session.call_tool(
        name="query_code_database",
        arguments={
            "query": query,
        },
    )


# Test util
async def main(host, port, transport, query, resource, tool):
    """Main asynchronous function to connect to the MCP server and execute commands.

    Used for local testing.

    Args:
        host: Server hostname.
        port: Server port.
        transport: Connection transport ('sse' or 'stdio').
        query: Optional query string for the 'find_agent' tool.
        resource: Optional resource URI to read.
        tool: Optional tool name to test.
    """
    logger.info("Starting Client to connect to MCP")
    async with init_session(host, port, transport) as session:
        if query:
            result = await find_agent(session, query)
            data = json.loads(result.content[0].text)
            logger.info(json.dumps(data, indent=2))
        if resource:
            result = await find_resource(session, resource)
            logger.info(result)
            data = json.loads(result.contents[0].text)
            logger.info(json.dumps(data, indent=2))
        if tool:
            if tool == "semantic_code_search":
                result = await semantic_code_search(
                    session, "find authentication functions", "*", "python"
                )
                data = json.loads(result.content[0].text)
                logger.info(json.dumps(data, indent=2))
            elif tool == "analyze_code_quality":
                result = await analyze_code_quality(
                    session, "backend/app/api/routes/agents.py", "comprehensive"
                )
                data = json.loads(result.content[0].text)
                logger.info(json.dumps(data, indent=2))
            elif tool == "generate_documentation":
                result = await generate_documentation(
                    session, "backend/app/api/routes/agents.py", "docstrings", "google"
                )
                data = json.loads(result.content[0].text)
                logger.info(json.dumps(data, indent=2))
            elif tool == "search_code_patterns":
                result = await search_code_patterns(
                    session, "async def", [".py"], ["__pycache__"]
                )
                data = json.loads(result.content[0].text)
                logger.info(json.dumps(data, indent=2))
            elif tool == "query_code_database":
                result = await query_code_database(
                    session, "SELECT * FROM functions WHERE is_async = true"
                )
                data = json.loads(result.content[0].text)
                logger.info(json.dumps(data, indent=2))


# Command line tester
@click.command()
@click.option("--host", default="localhost", help="SSE Host")
@click.option("--port", default="10100", help="SSE Port")
@click.option("--transport", default="stdio", help="MCP Transport")
@click.option("--find_agent", help="Query to find an agent")
@click.option("--resource", help="URI of the resource to locate")
@click.option(
    "--tool",
    help="Name of the tool to test (semantic_code_search, analyze_code_quality, generate_documentation, search_code_patterns, query_code_database)",
)
def cli(host, port, transport, find_agent, resource, tool):
    """A command-line client to interact with the Agent Cards MCP server."""
    asyncio.run(main(host, port, transport, find_agent, resource, tool))


if __name__ == "__main__":
    cli()
