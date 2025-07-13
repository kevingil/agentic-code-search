"""
Tests for EmbeddingService to verify REAL embedding functionality.
These tests use the actual Google API key from settings to generate real embeddings.
NO MOCKS - REAL EMBEDDINGS ONLY!
"""

import pytest
from app.services.embedding_service import EmbeddingService
from app.core.config import settings


class TestEmbeddingService:
    """Test suite for EmbeddingService - REAL EMBEDDINGS ONLY"""
    
    def test_service_initialization(self):
        """Test service initialization with real API key from settings"""
        # This will use the REAL API key from settings.GOOGLE_API_KEY
        service = EmbeddingService()
        
        # Should initialize successfully with real API key
        assert service.genai_available is True
        assert hasattr(service, 'temp_dir')
        assert service.EMBEDDING_MODEL == "models/text-embedding-004"
        
        # Clean up
        service.__del__()
    
    def test_supported_extensions(self):
        """Test that supported extensions are defined correctly"""
        service = EmbeddingService()
        
        # Should have supported extensions
        assert hasattr(service, 'SUPPORTED_EXTENSIONS')
        assert isinstance(service.SUPPORTED_EXTENSIONS, set)
        assert '.py' in service.SUPPORTED_EXTENSIONS
        assert '.js' in service.SUPPORTED_EXTENSIONS
        assert '.ts' in service.SUPPORTED_EXTENSIONS
        assert '.java' in service.SUPPORTED_EXTENSIONS
        assert '.cpp' in service.SUPPORTED_EXTENSIONS
        
        # Clean up
        service.__del__()
    
    def test_constants(self):
        """Test that service constants are defined"""
        service = EmbeddingService()
        
        # Check important constants exist
        assert hasattr(service, 'MAX_REPO_SIZE_MB')
        assert hasattr(service, 'MAX_FILE_SIZE_KB')
        assert hasattr(service, 'CHUNK_SIZE')
        assert hasattr(service, 'EMBEDDING_MODEL')
        
        # Check values are reasonable
        assert service.MAX_REPO_SIZE_MB > 0
        assert service.MAX_FILE_SIZE_KB > 0
        assert service.CHUNK_SIZE > 0
        assert service.EMBEDDING_MODEL.startswith('models/')
        
        # Clean up
        service.__del__()
    
    @pytest.mark.asyncio
    async def test_real_embedding_generation(self):
        """Test REAL embedding generation with actual Google GenAI API"""
        service = EmbeddingService()
        
        # Test with real content
        test_content = """
        def calculate_fibonacci(n):
            if n <= 1:
                return n
            return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)
        
        # This is a Python function that calculates Fibonacci numbers recursively
        """
        
        # Generate REAL embedding using Google API
        embedding = await service._generate_embedding(test_content)
        
        # Verify embedding properties
        assert isinstance(embedding, list)
        assert len(embedding) == 768  # Expected dimension for text-embedding-004
        assert all(isinstance(x, float) for x in embedding)
        
        # Verify embedding values are reasonable (not all zeros or ones)
        assert not all(x == 0.0 for x in embedding)
        assert not all(x == 1.0 for x in embedding)
        assert any(-1.0 <= x <= 1.0 for x in embedding)  # Values should be normalized
        
        # Test with different content to ensure different embeddings
        different_content = "This is completely different text about weather and climate patterns."
        different_embedding = await service._generate_embedding(different_content)
        
        # Different content should produce different embeddings
        assert embedding != different_embedding
        assert len(different_embedding) == 768
        
        # Clean up
        service.__del__()
    
    @pytest.mark.asyncio 
    async def test_content_truncation_with_real_api(self):
        """Test that very long content is properly truncated and still generates real embeddings"""
        service = EmbeddingService()
        
        # Create content longer than 30000 characters
        long_content = "This is a test sentence. " * 2000  # About 50,000 characters
        
        # Should still generate real embedding (truncated)
        embedding = await service._generate_embedding(long_content)
        
        assert isinstance(embedding, list)
        assert len(embedding) == 768
        assert all(isinstance(x, float) for x in embedding)
        
        # Clean up  
        service.__del__()
    
    def test_api_key_from_settings(self):
        """Verify that the API key is properly loaded from settings"""
        # This tests that settings.GOOGLE_API_KEY is accessible and configured
        assert hasattr(settings, 'GOOGLE_API_KEY')
        assert settings.GOOGLE_API_KEY is not None
        assert len(settings.GOOGLE_API_KEY) > 20  # Real API keys are longer than 20 chars
        
        # Test service uses this API key
        service = EmbeddingService()
        assert service.genai_available is True
        
        # Clean up
        service.__del__()
    
    @pytest.mark.asyncio
    async def test_embedding_consistency(self):
        """Test that the same content produces the same embedding consistently"""
        service = EmbeddingService()
        
        content = "def hello_world(): print('Hello, World!')"
        
        # Generate embedding twice
        embedding1 = await service._generate_embedding(content)
        embedding2 = await service._generate_embedding(content)
        
        # Should be exactly the same (Google's embedding model is deterministic)
        assert embedding1 == embedding2
        assert len(embedding1) == 768
        assert len(embedding2) == 768
        
        # Clean up
        service.__del__() 
