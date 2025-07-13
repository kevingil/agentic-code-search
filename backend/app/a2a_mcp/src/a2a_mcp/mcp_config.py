#!/usr/bin/env python3
"""
Configuration for the MCP Server.
This is a standalone configuration separate from the main app.
"""

import os
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerSettings(BaseSettings):
    """Settings for the MCP Server."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    model_config = SettingsConfigDict(
        # Use the local .env file in the MCP server directory
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Google API Key for AI services
    GOOGLE_API_KEY: str
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_SSLMODE: str

    # Optional: Google Places API Key
    GOOGLE_PLACES_API_KEY: str = ""

    # MCP Server Configuration
    MCP_HOST: str = "localhost"
    MCP_PORT: int = 10100
    MCP_TRANSPORT: str = "sse"


# Create a global instance
mcp_settings = MCPServerSettings()
