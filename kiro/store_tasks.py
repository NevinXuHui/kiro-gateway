# -*- coding: utf-8 -*-

"""
Task Management - In-Memory Store.

Thread-safe in-memory storage for tasks.
"""

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from kiro.models_tasks import Task, TaskCreate, TaskUpdate, TaskPatch, TaskStatus, TaskPriority


class TaskStore:
    """In-memory task storage with filtering and pagination."""

    def __init__(self):
        self._tasks: Dict[str, Task] = {}

    def create(self, data: TaskCreate) -> Task:
        """Create a new task."""
        task = Task(
            title=data.title,
            description=data.description,
            status=data.status,
            priority=data.priority,
        )
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def update(self, task_id: str, data: TaskUpdate) -> Optional[Task]:
        """Full update of a task (PUT)."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.title = data.title
        task.description = data.description
        task.status = data.status
        task.priority = data.priority
        task.updated_at = datetime.now(timezone.utc)
        return task

    def patch(self, task_id: str, data: TaskPatch) -> Optional[Task]:
        """Partial update of a task (PATCH)."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        patch_data = data.model_dump(exclude_unset=True)
        for field, value in patch_data.items():
            setattr(task, field, value)
        if patch_data:
            task.updated_at = datetime.now(timezone.utc)
        return task

    def delete(self, task_id: str) -> bool:
        """Delete a task. Returns True if deleted."""
        return self._tasks.pop(task_id, None) is not None

    def list(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Task], int]:
        """List tasks with filtering, sorting, and pagination."""
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if priority:
            tasks = [t for t in tasks if t.priority == priority]

        total = len(tasks)

        priority_order = {"high": 0, "medium": 1, "low": 2}
        if sort_by == "priority":
            tasks.sort(
                key=lambda t: priority_order.get(t.priority.value, 1),
                reverse=(sort_order == "desc"),
            )
        elif sort_by in ("created_at", "updated_at"):
            tasks.sort(
                key=lambda t: getattr(t, sort_by),
                reverse=(sort_order == "desc"),
            )

        start = (page - 1) * page_size
        tasks = tasks[start : start + page_size]

        return tasks, total
