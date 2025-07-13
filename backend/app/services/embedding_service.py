import os
import tempfile
import shutil
import uuid
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
import asyncio
from datetime import datetime
import subprocess
import mimetypes
from sqlmodel import Session, select
import google.generativeai as genai

from app.core.db import engine
from app.models import CodeSearchSession, CodeSearchEmbedding
from app.core.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Service for generating embeddings from GitHub repositories using Google Generative AI.
    
    This service downloads GitHub repositories, processes code files, and generates
    vector embeddings for semantic code search. It includes:
    
    - Repository download via git clone
    - File filtering and content processing
    - Text chunking for large files
    - Real embedding generation using Google's text-embedding-004 model
    - Rate limiting and retry logic
    - Fallback to deterministic placeholder embeddings
    
    Configuration:
    - Requires GOOGLE_API_KEY environment variable or settings.GOOGLE_API_KEY
    - Automatically falls back to placeholder embeddings if API key is missing
    
    Usage:
        service = EmbeddingService()
        await service.generate_embeddings_for_session(session_id, github_url)
    """
    
    # Configuration constants
    MAX_REPO_SIZE_MB = 100  # Maximum repo size in MB
    MAX_FILE_SIZE_KB = 200  # Maximum individual file size in KB
    MAX_FILES_TO_PROCESS = 1000  # Maximum number of files to process
    CHUNK_SIZE = 1000  # Size of each text chunk for embedding
    MAX_EMBEDDINGS_PER_SESSION = 2000  # Maximum embeddings per session
    
    # Embedding model configuration
    EMBEDDING_MODEL = "models/text-embedding-004"
    
    # Supported file extensions for code analysis
    SUPPORTED_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
        '.cs', '.rb', '.go', '.rs', '.php', '.swift', '.kt', '.scala',
        '.sql', '.html', '.css', '.scss', '.sass', '.less', '.xml', '.json',
        '.yaml', '.yml', '.md', '.txt', '.sh', '.bash', '.zsh', '.fish',
        '.dockerfile', '.makefile', '.gradle', '.maven', '.cmake',
        '.r', '.R', '.jl', '.m', '.pl', '.lua', '.vim', '.config'
    }
    
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="code_search_")
        
        # Configure Google Generative AI
        api_key = getattr(settings, 'GOOGLE_API_KEY', None) or os.getenv('GOOGLE_API_KEY')
        if not api_key:
            logger.error("Google API key not found. Please set GOOGLE_API_KEY in environment variables or settings.")
            self.genai_available = False
        else:
            try:
                genai.configure(api_key=api_key)
                self.genai_available = True
                logger.info("Google GenAI configured for embeddings successfully")
            except Exception as e:
                logger.error(f"Failed to configure Google GenAI: {e}")
                self.genai_available = False
                raise ValueError(f"Failed to configure Google GenAI with provided API key: {e}") from e
        
    def __del__(self):
        """Clean up temp directory"""
        try:
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass
    
    async def generate_embeddings_for_session(self, session_id: uuid.UUID, github_url: str):
        """
        Generate embeddings for a session by downloading and processing the repository.
        This runs in the background.
        """
        try:
            logger.info(f"Starting embedding generation for session {session_id}")
            
            # Update session status
            with Session(engine) as session:
                db_session = session.get(CodeSearchSession, session_id)
                if not db_session:
                    logger.error(f"Session {session_id} not found")
                    return
                
                db_session.vector_embeddings_processed = False
                db_session.updated_at = datetime.utcnow()
                session.add(db_session)
                session.commit()
            
            # Download repository
            repo_path = await self._download_repository(github_url)
            if not repo_path:
                logger.error(f"Failed to download repository {github_url}")
                return
            
            # Process files and generate embeddings
            await self._process_repository(session_id, repo_path)
            
            # Mark session as processed
            with Session(engine) as session:
                db_session = session.get(CodeSearchSession, session_id)
                if db_session:
                    db_session.vector_embeddings_processed = True
                    db_session.updated_at = datetime.utcnow()
                    session.add(db_session)
                    session.commit()
            
            logger.info(f"Completed embedding generation for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error generating embeddings for session {session_id}: {e}")
            # Mark session as failed
            with Session(engine) as session:
                db_session = session.get(CodeSearchSession, session_id)
                if db_session:
                    db_session.vector_embeddings_processed = False
                    db_session.updated_at = datetime.utcnow()
                    session.add(db_session)
                    session.commit()
        finally:
            # Clean up downloaded repo
            if 'repo_path' in locals() and repo_path and os.path.exists(repo_path):
                try:
                    shutil.rmtree(repo_path)
                except:
                    pass
    
    async def _download_repository(self, github_url: str) -> Optional[str]:
        """Download repository using git clone"""
        try:
            # Create unique directory for this download
            repo_name = github_url.split('/')[-1].replace('.git', '')
            repo_path = os.path.join(self.temp_dir, f"{repo_name}_{uuid.uuid4().hex[:8]}")
            
            # Clone repository (shallow clone for speed)
            cmd = [
                'git', 'clone', '--depth', '1', '--single-branch',
                github_url, repo_path
            ]
            
            # Run git clone with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)  # 5 minute timeout
            except asyncio.TimeoutError:
                process.kill()
                logger.error(f"Git clone timed out for {github_url}")
                return None
            
            if process.returncode != 0:
                logger.error(f"Git clone failed for {github_url}: {stderr.decode()}")
                return None
            
            # Check repository size
            repo_size = await self._get_directory_size(repo_path)
            if repo_size > self.MAX_REPO_SIZE_MB * 1024 * 1024:
                logger.warning(f"Repository {github_url} is too large ({repo_size / (1024*1024):.2f} MB)")
                return None
            
            logger.info(f"Downloaded repository {github_url} to {repo_path}")
            return repo_path
            
        except Exception as e:
            logger.error(f"Error downloading repository {github_url}: {e}")
            return None
    
    async def _get_directory_size(self, path: str) -> int:
        """Get total size of directory in bytes"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        if os.path.isfile(file_path):
                            total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        continue
        except Exception as e:
            logger.error(f"Error calculating directory size: {e}")
        return total_size
    
    async def _process_repository(self, session_id: uuid.UUID, repo_path: str):
        """Process repository files and generate embeddings"""
        try:
            logger.info(f"Processing repository at {repo_path}")
            
            # Get all relevant files
            files_to_process = await self._get_files_to_process(repo_path)
            logger.info(f"Found {len(files_to_process)} files to process")
            
            # Limit number of files
            if len(files_to_process) > self.MAX_FILES_TO_PROCESS:
                files_to_process = files_to_process[:self.MAX_FILES_TO_PROCESS]
                logger.warning(f"Limited to {self.MAX_FILES_TO_PROCESS} files")
            
            embedding_count = 0
            
            # Process each file
            for file_path in files_to_process:
                if embedding_count >= self.MAX_EMBEDDINGS_PER_SESSION:
                    logger.warning(f"Reached maximum embeddings limit ({self.MAX_EMBEDDINGS_PER_SESSION})")
                    break
                
                try:
                    # Get relative path from repo root
                    relative_path = os.path.relpath(file_path, repo_path)
                    
                    # Read file content
                    content = await self._read_file_content(file_path)
                    if not content:
                        continue
                    
                    # Create chunks if content is large
                    chunks = self._create_chunks(content, self.CHUNK_SIZE)
                    
                    # Generate embeddings for each chunk
                    for chunk_index, chunk in enumerate(chunks):
                        if embedding_count >= self.MAX_EMBEDDINGS_PER_SESSION:
                            break
                        
                        # Generate embedding vector
                        embedding_vector = await self._generate_embedding(chunk)
                        
                        # Create embedding record
                        embedding = CodeSearchEmbedding(
                            session_id=session_id,
                            file_path=relative_path,
                            file_content=chunk,
                            chunk_index=chunk_index,
                            chunk_size=len(chunk),
                            embedding_vector=embedding_vector,
                            file_metadata=self._get_file_metadata(file_path)
                        )
                        
                        # Save to database
                        with Session(engine) as session:
                            session.add(embedding)
                            session.commit()
                        
                        embedding_count += 1
                        
                        # Small delay to avoid hitting rate limits too aggressively
                        if self.genai_available and embedding_count % 10 == 0:
                            await asyncio.sleep(0.1)  # 100ms delay every 10 embeddings
                        
                        # Log progress
                        if embedding_count % 50 == 0:
                            logger.info(f"Processed {embedding_count} embeddings for session {session_id}")
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                    continue
            
            logger.info(f"Generated {embedding_count} embeddings for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error processing repository: {e}")
            raise
    
    async def _get_files_to_process(self, repo_path: str) -> List[str]:
        """Get list of files to process from repository"""
        files_to_process = []
        
        try:
            for root, dirs, files in os.walk(repo_path):
                # Skip common directories that shouldn't be processed
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                    'node_modules', '__pycache__', '.git', '.vscode', '.idea',
                    'build', 'dist', 'target', 'bin', 'obj', 'venv', 'env'
                }]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # Skip hidden files and large files
                    if file.startswith('.'):
                        continue
                    
                    try:
                        file_size = os.path.getsize(file_path)
                        if file_size > self.MAX_FILE_SIZE_KB * 1024:
                            continue
                    except (OSError, IOError):
                        continue
                    
                    # Check file extension
                    ext = Path(file).suffix.lower()
                    if ext in self.SUPPORTED_EXTENSIONS:
                        files_to_process.append(file_path)
                    elif not ext and self._is_text_file(file_path):
                        # Handle files without extensions that are text files
                        files_to_process.append(file_path)
        
        except Exception as e:
            logger.error(f"Error getting files to process: {e}")
        
        return files_to_process
    
    def _is_text_file(self, file_path: str) -> bool:
        """Check if file is a text file"""
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and mime_type.startswith('text/'):
                return True
            
            # Check if file content is text
            with open(file_path, 'rb') as f:
                sample = f.read(1024)
                try:
                    sample.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    return False
        except:
            return False
    
    async def _read_file_content(self, file_path: str) -> Optional[str]:
        """Read file content safely"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None
    
    def _create_chunks(self, content: str, chunk_size: int) -> List[str]:
        """Create chunks from content"""
        if len(content) <= chunk_size:
            return [content]
        
        chunks = []
        start = 0
        while start < len(content):
            end = start + chunk_size
            # Try to break at word boundaries
            if end < len(content):
                # Look for newline or space within last 100 characters
                last_newline = content.rfind('\n', start, end)
                last_space = content.rfind(' ', start, end)
                
                if last_newline > start:
                    end = last_newline
                elif last_space > start:
                    end = last_space
            
            chunks.append(content[start:end])
            start = end
        
        return chunks
    
    async def _generate_embedding(self, content: str) -> List[float]:
        """Generate embedding vector for content using Google Generative AI"""
        if not self.genai_available:
            raise ValueError(
                "Google API key not configured. Please set GOOGLE_API_KEY in environment variables "
                "or settings to generate embeddings."
            )
        
        # Retry logic for rate limiting
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                # Truncate content if too long (genai has token limits)
                max_chars = 30000  # Conservative limit
                if len(content) > max_chars:
                    content = content[:max_chars]
                    logger.debug(f"Truncated content to {max_chars} characters for embedding")
                
                # Generate embedding using Google Generative AI
                response = genai.embed_content(
                    model=self.EMBEDDING_MODEL,
                    content=content,
                    task_type='retrieval_document'
                )
                
                return response['embedding']
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for embedding generation: {e}")
                
                # Check if this is a rate limit error and we have retries left
                if attempt < max_retries - 1:
                    if "rate limit" in str(e).lower() or "quota" in str(e).lower():
                        logger.info(f"Rate limited, retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                
                # If all retries failed, raise the error
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} attempts failed for embedding generation: {e}")
                    raise RuntimeError(f"Failed to generate embedding after {max_retries} attempts: {e}") from e
    
    def _get_file_metadata(self, file_path: str) -> str:
        """Get file metadata as JSON string"""
        try:
            stat = os.stat(file_path)
            metadata = {
                'file_size': stat.st_size,
                'file_extension': Path(file_path).suffix,
                'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
            return str(metadata)
        except Exception as e:
            logger.error(f"Error getting file metadata: {e}")
            return "{}" 
