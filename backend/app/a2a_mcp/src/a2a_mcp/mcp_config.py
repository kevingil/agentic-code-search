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
        env_file_path = Path(__file__).parent.parent.parent / ".env"
        print(f"DEBUG: MCPServerSettings.__init__ - env_file_path = {env_file_path}")
        print(f"DEBUG: MCPServerSettings.__init__ - env_file_path exists = {env_file_path.exists()}")
        if env_file_path.exists():
            print(f"DEBUG: MCPServerSettings.__init__ - env_file_path absolute = {env_file_path.absolute()}")
        super().__init__(**kwargs)
    
    model_config = SettingsConfigDict(
        # Use the local .env file in the MCP server directory
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    
    # Google API Key for AI services
    GOOGLE_API_KEY: str
    
    # Optional: Google Places API Key
    GOOGLE_PLACES_API_KEY: str = ""
    
    # MCP Server Configuration
    MCP_HOST: str = "localhost"
    MCP_PORT: int = 10100
    MCP_TRANSPORT: str = "sse"

# Create a global instance
mcp_settings = MCPServerSettings()

# Debug: Print the loaded settings
print(f"DEBUG: mcp_config.py - Loaded GOOGLE_API_KEY = '{mcp_settings.GOOGLE_API_KEY}'")
print(f"DEBUG: mcp_config.py - GOOGLE_API_KEY length = {len(mcp_settings.GOOGLE_API_KEY)}")
print(f"DEBUG: mcp_config.py - GOOGLE_API_KEY type = {type(mcp_settings.GOOGLE_API_KEY)}")
print(f"DEBUG: mcp_config.py - GOOGLE_API_KEY repr = {repr(mcp_settings.GOOGLE_API_KEY)}") 
