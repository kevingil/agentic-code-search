#!/usr/bin/env python3
"""
Main entry point for a2a_mcp package.
This allows running the package as a standalone module with:
python -m app.a2a_mcp --run mcp-server --transport sse --host localhost --port 10100
"""

from .src.a2a_mcp import main

if __name__ == '__main__':
    main() 
