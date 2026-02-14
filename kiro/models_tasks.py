# -*- coding: utf-8 -*-

"""
Task Management - Pydantic Models.

Data models for task CRUD operations.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task status options."""
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class TaskPriority(str, Enum):
    """Task priority levels."""
    low = "low"
    medium = "medium"
    high = "high"


class TaskCreate(BaseModel):
    """Request body for creating a task."""
    title: str = Field(..., min_length=1, max_length=200, description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    status: TaskStatus = Field(TaskStatus.pending, description="Task status")
    priority: TaskPriority = Field(TaskPriority.medium, description="Task priority")


class TaskUpdate(BaseModel):
    """Request body for full update (PUT)."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.pending
    priority: TaskPriority = TaskPriority.medium


class TaskPatch(BaseModel):
    """Request body for partial update (PATCH)."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None


class Task(BaseModel):
    """Complete task representation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.pending
    priority: TaskPriority = TaskPriority.medium
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskListResponse(BaseModel):
    """Paginated task list response."""
    tasks: List[Task]
    total: int
    page: int
    page_size: int
    total_pages: int
