# type: ignore
import logging
import os

import google.generativeai as genai

from ..mcp_config import mcp_settings
from .types import ServerConfig


logger = logging.getLogger(__name__)


def init_api_key():
    """Initialize the API key for Google Generative AI."""
    print(f"DEBUG: init_api_key() - mcp_settings.GOOGLE_API_KEY = '{mcp_settings.GOOGLE_API_KEY}'")
    print(f"DEBUG: init_api_key() - len(mcp_settings.GOOGLE_API_KEY) = {len(mcp_settings.GOOGLE_API_KEY)}")
    if not mcp_settings.GOOGLE_API_KEY:
        logger.error('GOOGLE_API_KEY is not set')
        raise ValueError('GOOGLE_API_KEY is not set')

    genai.configure(api_key=mcp_settings.GOOGLE_API_KEY)
    print(f"DEBUG: init_api_key() - genai.configure() completed")


def config_logging():
    """Configure basic logging."""
    log_level = (
        os.getenv('A2A_LOG_LEVEL') or os.getenv('FASTMCP_LOG_LEVEL') or 'INFO'
    ).upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))


def config_logger(logger):
    """Logger specific config, avoiding clutter in enabling all loggging."""
    # TODO: replace with env
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def get_mcp_server_config() -> ServerConfig:
    """Get the MCP server configuration."""
    return ServerConfig(
        host=mcp_settings.MCP_HOST,
        port=mcp_settings.MCP_PORT,
        transport=mcp_settings.MCP_TRANSPORT,
        url=f'http://{mcp_settings.MCP_HOST}:{mcp_settings.MCP_PORT}/sse',
    )
