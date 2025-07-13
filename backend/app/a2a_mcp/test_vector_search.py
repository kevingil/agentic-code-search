#!/usr/bin/env python3
"""
Test script for vector search functionality in MCP server.
This script tests the database connection and basic vector search operations.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the src directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from a2a_mcp.mcp.db_connection import VectorSearchService, get_mcp_session
from a2a_mcp.mcp_config import mcp_settings


async def test_database_connection():
    """Test basic database connection."""
    print("Testing database connection...")
    try:
        with get_mcp_session() as session:
            # Simple query to test connection  
            from sqlmodel import text
            result = session.exec(text("SELECT 1 as test"))
            row = result.first()
            if row and row.test == 1:
                print("✅ Database connection successful")
                return True
            else:
                print("❌ Database connection failed: unexpected result")
                return False
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def test_vector_search_service():
    """Test vector search service initialization."""
    print("\nTesting VectorSearchService initialization...")
    try:
        service = VectorSearchService()
        print("✅ VectorSearchService initialized successfully")
        return service
    except Exception as e:
        print(f"❌ VectorSearchService initialization failed: {e}")
        return None


async def test_get_sessions():
    """Test getting sessions with embeddings."""
    print("\nTesting get_sessions_with_embeddings...")
    try:
        service = VectorSearchService()
        sessions = await service.get_sessions_with_embeddings()
        print(f"✅ Found {len(sessions)} sessions with embeddings")
        
        if sessions:
            print("\nFirst session details:")
            session = sessions[0]
            for key, value in session.items():
                if key == 'id':
                    print(f"  {key}: {value}")
                elif key in ['name', 'github_url', 'embedding_count']:
                    print(f"  {key}: {value}")
        
        return True
    except Exception as e:
        print(f"❌ get_sessions_with_embeddings failed: {e}")
        return False


async def test_search_functionality():
    """Test basic search functionality if embeddings exist."""
    print("\nTesting search functionality...")
    try:
        service = VectorSearchService()
        sessions = await service.get_sessions_with_embeddings()
        
        if not sessions:
            print("ℹ️  No sessions with embeddings found - skipping search test")
            return True
        
        # Test file path search
        results = await service.search_by_file_path("%.py")
        print(f"✅ File path search returned {len(results)} Python files")
        
        if results:
            print(f"  Example file: {results[0]['file_path']}")
        
        return True
    except Exception as e:
        print(f"❌ Search functionality test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("Starting Vector Search Tests")
    print("=" * 50)
    
    # Test configuration
    print("Configuration:")
    print(f"  Database URI: {str(mcp_settings.DATABASE_URI)}")
    print(f"  Google API Key configured: {'Yes' if mcp_settings.GOOGLE_API_KEY else 'No'}")
    print()
    
    # Run tests
    tests = [
        test_database_connection(),
        test_vector_search_service(),
        test_get_sessions(),
        test_search_functionality()
    ]
    
    results = await asyncio.gather(*tests, return_exceptions=True)
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    
    passed = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  Test {i+1}: ❌ FAILED ({result})")
        elif result:
            print(f"  Test {i+1}: ✅ PASSED")
            passed += 1
        else:
            print(f"  Test {i+1}: ❌ FAILED")
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Vector search is ready to use.")
    else:
        print("⚠️  Some tests failed. Check configuration and database setup.")


if __name__ == "__main__":
    asyncio.run(main()) 
