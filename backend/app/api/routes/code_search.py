import uuid
from typing import Any, List, Optional
from datetime import datetime
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlmodel import func, select, col
from urllib.parse import urlparse
import re

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    CodeSearchSession,
    CodeSearchSessionCreate,
    CodeSearchSessionUpdate,
    CodeSearchSessionPublic,
    CodeSearchSessionsPublic,
    Message,
)
from app.services.embedding_service import EmbeddingService

router = APIRouter(prefix="/code-search", tags=["code-search"])

# Initialize embedding service
embedding_service = EmbeddingService()

def extract_repo_name_from_url(url: str) -> str:
    """Extract repository name from GitHub URL"""
    try:
        # Remove trailing slash and fragments
        clean_url = url.rstrip("/").split("#")[0].split("?")[0]
        
        # Handle different GitHub URL formats
        patterns = [
            r"github\.com/([^/]+/[^/]+)/?$",  # https://github.com/owner/repo
            r"github\.com/([^/]+/[^/]+)/tree/.*$",  # https://github.com/owner/repo/tree/branch
            r"github\.com/([^/]+/[^/]+)/.*$",  # https://github.com/owner/repo/anything
        ]
        
        for pattern in patterns:
            match = re.search(pattern, clean_url)
            if match:
                return match.group(1)
        
        raise ValueError("Could not extract repository name")
    except Exception as e:
        raise ValueError(f"Invalid GitHub URL: {e}")

def is_valid_github_url(url: str) -> bool:
    """Validate GitHub URL format"""
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in ("http", "https") and
            parsed.netloc == "github.com" and
            bool(extract_repo_name_from_url(url))
        )
    except:
        return False

@router.get("/sessions", response_model=CodeSearchSessionsPublic)
def get_user_sessions(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100
) -> Any:
    """Get all code search sessions for the current user"""
    
    # Count total sessions
    count_statement = (
        select(func.count())
        .select_from(CodeSearchSession)
        .where(CodeSearchSession.owner_id == current_user.id)
    )
    count = session.exec(count_statement).one()
    
    # Get sessions ordered by last_used (most recent first)
    statement = (
        select(CodeSearchSession)
        .where(CodeSearchSession.owner_id == current_user.id)
        .order_by(CodeSearchSession.last_used.desc())
        .offset(skip)
        .limit(limit)
    )
    sessions = session.exec(statement).all()
    
    return CodeSearchSessionsPublic(data=sessions, count=count)

@router.post("/sessions", response_model=CodeSearchSessionPublic)
def create_session(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    session_in: CodeSearchSessionCreate
) -> Any:
    """Create a new code search session"""
    
    # Validate GitHub URL if provided
    if session_in.github_url:
        if not is_valid_github_url(session_in.github_url):
            raise HTTPException(
                status_code=400,
                detail="Invalid GitHub URL. Please provide a valid GitHub repository URL."
            )
        
        # Extract repository name for uniqueness check
        try:
            repo_name = extract_repo_name_from_url(session_in.github_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Check if user already has a session for this repository
        existing_session = session.exec(
            select(CodeSearchSession).where(
                CodeSearchSession.owner_id == current_user.id,
                CodeSearchSession.github_url == session_in.github_url
            )
        ).first()
        
        if existing_session:
            # Update last_used and return existing session
            existing_session.last_used = datetime.now(datetime.UTC)
            session.add(existing_session)
            session.commit()
            session.refresh(existing_session)
            return existing_session
    
    # Create new session
    db_session = CodeSearchSession.model_validate(
        session_in, 
        update={"owner_id": current_user.id}
    )
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    # Start background embedding generation if GitHub URL provided
    if session_in.github_url:
        background_tasks.add_task(
            embedding_service.generate_embeddings_for_session,
            db_session.id,
            session_in.github_url
        )
    
    return db_session

@router.get("/sessions/{session_id}", response_model=CodeSearchSessionPublic)
def get_session(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
) -> Any:
    """Get a specific code search session"""
    
    db_session = session.exec(
        select(CodeSearchSession).where(
            CodeSearchSession.id == session_id,
            CodeSearchSession.owner_id == current_user.id
        )
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return db_session

@router.put("/sessions/{session_id}", response_model=CodeSearchSessionPublic)
def update_session(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    session_update: CodeSearchSessionUpdate
) -> Any:
    """Update a code search session"""
    
    db_session = session.exec(
        select(CodeSearchSession).where(
            CodeSearchSession.id == session_id,
            CodeSearchSession.owner_id == current_user.id
        )
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update fields
    session_data = session_update.model_dump(exclude_unset=True)
    session_data["updated_at"] = datetime.now(datetime.UTC)
    
    for field, value in session_data.items():
        setattr(db_session, field, value)
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    return db_session

@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
) -> Message:
    """Delete a code search session"""
    
    db_session = session.exec(
        select(CodeSearchSession).where(
            CodeSearchSession.id == session_id,
            CodeSearchSession.owner_id == current_user.id
        )
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.delete(db_session)
    session.commit()
    
    return Message(message="Session deleted successfully")

@router.get("/sessions/{session_id}/embeddings-status")
def get_embeddings_status(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
) -> Any:
    """Get the embeddings processing status for a session"""
    
    db_session = session.exec(
        select(CodeSearchSession).where(
            CodeSearchSession.id == session_id,
            CodeSearchSession.owner_id == current_user.id
        )
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get embeddings count
    embeddings_count = len(db_session.embeddings) if db_session.embeddings else 0
    
    return {
        "session_id": session_id,
        "embeddings_processed": db_session.vector_embeddings_processed,
        "embeddings_count": embeddings_count,
        "created_at": db_session.created_at,
        "updated_at": db_session.updated_at
    }

@router.post("/sessions/{session_id}/regenerate-embeddings")
def regenerate_embeddings(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks
) -> Message:
    """Regenerate embeddings for a session"""
    
    db_session = session.exec(
        select(CodeSearchSession).where(
            CodeSearchSession.id == session_id,
            CodeSearchSession.owner_id == current_user.id
        )
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not db_session.github_url:
        raise HTTPException(
            status_code=400,
            detail="Cannot regenerate embeddings for sessions without a GitHub URL"
        )
    
    # Reset embeddings status
    db_session.vector_embeddings_processed = False
    db_session.updated_at = datetime.now(datetime.UTC)
    session.add(db_session)
    session.commit()
    
    # Start background embedding generation
    background_tasks.add_task(
        embedding_service.generate_embeddings_for_session,
        session_id,
        db_session.github_url
    )
    
    return Message(message="Embeddings regeneration started") 
