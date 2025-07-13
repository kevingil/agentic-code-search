import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel, Column
from sqlalchemy import Text
from pgvector.sqlalchemy import Vector


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=40)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=40)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)
    code_search_sessions: list["CodeSearchSession"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Code Search Session Models
class CodeSearchSessionBase(SQLModel):
    name: str = Field(max_length=255)
    github_url: Optional[str] = Field(default=None, max_length=500)
    agent_type: str = Field(default="orchestrator", max_length=100)
    is_active: bool = Field(default=True)
    vector_embeddings_processed: bool = Field(default=False)
    last_used: datetime = Field(default_factory=datetime.utcnow)


# Properties to receive via API on creation
class CodeSearchSessionCreate(CodeSearchSessionBase):
    pass


# Properties to receive via API on update
class CodeSearchSessionUpdate(SQLModel):
    name: Optional[str] = Field(default=None, max_length=255)
    github_url: Optional[str] = Field(default=None, max_length=500)
    agent_type: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
    vector_embeddings_processed: Optional[bool] = None
    last_used: Optional[datetime] = None


# Database model for code search sessions
class CodeSearchSession(CodeSearchSessionBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    owner: User | None = Relationship(back_populates="code_search_sessions")
    embeddings: list["CodeSearchEmbedding"] = Relationship(back_populates="session", cascade_delete=True)


# Properties to return via API
class CodeSearchSessionPublic(CodeSearchSessionBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CodeSearchSessionsPublic(SQLModel):
    data: list[CodeSearchSessionPublic]
    count: int


# Code Search Embedding Models
class CodeSearchEmbeddingBase(SQLModel):
    file_path: str = Field(max_length=1000)
    file_content: str = Field(max_length=100000)  # Large text field for file content
    chunk_index: int = Field(default=0)  # For splitting large files into chunks
    chunk_size: int = Field(default=1000)  # Size of each chunk
    embedding_vector: Optional[List[float]] = Field(default=None)  # Vector embedding as list of floats
    file_metadata: Optional[str] = Field(default=None, max_length=5000)  # JSON string for additional metadata


# Properties to receive via API on creation
class CodeSearchEmbeddingCreate(CodeSearchEmbeddingBase):
    session_id: uuid.UUID


# Properties to receive via API on update
class CodeSearchEmbeddingUpdate(SQLModel):
    file_path: Optional[str] = Field(default=None, max_length=1000)
    file_content: Optional[str] = Field(default=None, max_length=100000)
    chunk_index: Optional[int] = None
    chunk_size: Optional[int] = None
    embedding_vector: Optional[List[float]] = Field(default=None)
    file_metadata: Optional[str] = Field(default=None, max_length=5000)


# Database model for code search embeddings
class CodeSearchEmbedding(CodeSearchEmbeddingBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(
        foreign_key="codesearchsession.id", nullable=False, ondelete="CASCADE"
    )
    # Override the embedding_vector field to use pgvector's VECTOR type
    embedding_vector: Optional[List[float]] = Field(
        default=None, 
        sa_column=Column(Vector(1536))  # 1536 is common for OpenAI embeddings, adjust as needed
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    session: CodeSearchSession | None = Relationship(back_populates="embeddings")


# Properties to return via API
class CodeSearchEmbeddingPublic(CodeSearchEmbeddingBase):
    id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime


class CodeSearchEmbeddingsPublic(SQLModel):
    data: list[CodeSearchEmbeddingPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)
