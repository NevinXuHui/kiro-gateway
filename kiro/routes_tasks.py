# -*- coding: utf-8 -*-

"""
Task Management - API Routes.

CRUD endpoints for task management at /v1/tasks.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.models_tasks import (
    Task,
    TaskCreate,
    TaskUpdate,
    TaskPatch,
    TaskListResponse,
    TaskStatus,
    TaskPriority,
)
from kiro.store_tasks import TaskStore

# --- Security (reuse same scheme as other routes) ---
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(request: Request, auth_header: str = Security(api_key_header)) -> bool:
    """Verify API key in Authorization header via ApiKeyManager."""
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    token = auth_header[7:]
    manager = request.app.state.apikey_manager
    if not manager.verify_key(token):
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


# --- Router & Store ---
router = APIRouter(prefix="/v1/tasks", dependencies=[Depends(verify_api_key)])
store = TaskStore()


@router.post("", response_model=Task, status_code=201)
async def create_task(data: TaskCreate):
    """Create a new task."""
    task = store.create(data)
    logger.info(f"Task created: {task.id} - {task.title}")
    return task


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: TaskStatus | None = Query(None, description="Filter by status"),
    priority: TaskPriority | None = Query(None, description="Filter by priority"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|priority)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """List tasks with filtering, sorting, and pagination."""
    tasks, total = store.list(
        status=status, priority=priority,
        page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )
    return TaskListResponse(
        tasks=tasks, total=total, page=page, page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str):
    """Get a single task by ID."""
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=Task)
async def update_task(task_id: str, data: TaskUpdate):
    """Full update of a task."""
    task = store.update(task_id, data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info(f"Task updated: {task_id}")
    return task


@router.patch("/{task_id}", response_model=Task)
async def patch_task(task_id: str, data: TaskPatch):
    """Partial update of a task."""
    task = store.patch(task_id, data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info(f"Task patched: {task_id}")
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str):
    """Delete a task."""
    if not store.delete(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info(f"Task deleted: {task_id}")
