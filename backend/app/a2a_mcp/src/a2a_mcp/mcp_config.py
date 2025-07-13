#!/usr/bin/env python3
"""
Configuration for the MCP Server.
This is a standalone configuration separate from the main app.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_core import MultiHostUrl
from pydantic import PostgresDsn


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
    
    # Database configuration for PostgreSQL (optional - only needed for vector search tools)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URI(self) -> Optional[PostgresDsn]:
        """Build the database URI for SQLAlchemy. Returns None if database config is incomplete."""
        if not all([self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_DB]):
            return None
        return MultiHostUrl.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    # Optional: Google Places API Key
    GOOGLE_PLACES_API_KEY: str = ""

    # MCP Server Configuration
    MCP_HOST: str = "localhost"
    MCP_PORT: int = 10100
    MCP_TRANSPORT: str = "sse"


# Create a global instance
mcp_settings = MCPServerSettings()
