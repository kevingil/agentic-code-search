# Vector Search Tools for MCP Server

This document describes the vector search tools available in the Agent-to-Agent MCP Server for performing semantic code search on processed repository embeddings.

## Overview

The vector search tools allow you to perform semantic search on code repositories that have been processed by the embedding service. These tools use vector embeddings generated with Google's `text-embedding-004` model to find semantically similar code chunks based on natural language queries.

## Prerequisites

1. **Database Configuration**: Ensure your `.env` file contains the necessary PostgreSQL connection parameters:
   ```env
   POSTGRES_SERVER=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=your_db_user
   POSTGRES_PASSWORD=your_db_password
   POSTGRES_DB=your_db_name
   GOOGLE_API_KEY=your_google_api_key
   ```

2. **Processed Embeddings**: The repository must have been processed by the main application's embedding service and have `vector_embeddings_processed=true`.

## Available Tools

### 1. `vector_search_code`

Search for similar code chunks using natural language queries.

**Parameters:**
- `query` (string, required): Natural language description of what you're looking for
- `session_id` (string, optional): UUID of specific session to search within
- `limit` (integer, optional): Maximum number of results (default: 10, max: 50)
- `similarity_threshold` (float, optional): Minimum similarity score 0-1 (default: 0.7)

**Example:**
```json
{
  "query": "function that calculates fibonacci numbers",
  "limit": 5,
  "similarity_threshold": 0.8
}
```

### 2. `list_code_sessions`

List all code search sessions that have processed vector embeddings.

**Parameters:** None

**Returns:** List of sessions with metadata including embedding counts.

### 3. `get_session_files`

Get all files and their chunk information for a specific code search session.

**Parameters:**
- `session_id` (string, required): UUID of the session to get files for

**Example:**
```json
{
  "session_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### 4. `search_code_by_file_path`

Search for code chunks by file path pattern.

**Parameters:**
- `file_path_pattern` (string, required): SQL LIKE pattern for file paths (use % for wildcards)
- `session_id` (string, optional): UUID of specific session to search within

**Example:**
```json
{
  "file_path_pattern": "%.py",
  "session_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### 5. `generate_query_embedding`

Generate an embedding vector for a text query (useful for debugging).

**Parameters:**
- `text` (string, required): The text to generate an embedding for

**Example:**
```json
{
  "text": "authentication function"
}
```

## Usage Examples

### Finding Authentication Code
```json
{
  "tool": "vector_search_code",
  "parameters": {
    "query": "user authentication and login validation",
    "limit": 10,
    "similarity_threshold": 0.75
  }
}
```

### Finding All Python Files in a Session
```json
{
  "tool": "search_code_by_file_path",
  "parameters": {
    "file_path_pattern": "%.py",
    "session_id": "your-session-uuid"
  }
}
```

### Finding Database Connection Code
```json
{
  "tool": "vector_search_code",
  "parameters": {
    "query": "database connection setup and configuration",
    "limit": 15
  }
}
```

## Response Format

All tools return JSON responses with the following general structure:

```json
{
  "query": "original query",
  "total_results": 5,
  "results": [
    {
      "id": "embedding-uuid",
      "session_id": "session-uuid",
      "session_name": "Repository Name",
      "github_url": "https://github.com/user/repo",
      "file_path": "src/auth/login.py",
      "file_content": "def authenticate_user(username, password):\n    ...",
      "chunk_index": 0,
      "chunk_size": 1000,
      "similarity": 0.85,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

## Error Handling

All tools include comprehensive error handling and will return JSON responses with error messages:

```json
{
  "error": "Invalid session_id format. Must be a valid UUID."
}
```

## Performance Considerations

- **Similarity Threshold**: Higher thresholds (0.8-0.9) return more precise but fewer results
- **Limit**: Use appropriate limits to avoid overwhelming responses
- **Session Filtering**: Use session_id when possible to improve performance
- **Query Quality**: More specific queries generally return better results

## Integration with Main Application

These tools work seamlessly with repositories processed by the main application's `EmbeddingService`. To use these tools:

1. Use the main application to process a GitHub repository
2. Wait for `vector_embeddings_processed` to be `true`
3. Use the MCP tools to search the processed embeddings

## Troubleshooting

- **No Results**: Try lowering the similarity threshold or making your query more general
- **Database Connection Errors**: Verify your PostgreSQL connection parameters
- **Invalid UUIDs**: Ensure session IDs are valid UUIDs
- **API Key Errors**: Verify your Google API key is correctly configured 
