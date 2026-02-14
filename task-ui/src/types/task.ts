export type TaskStatus = 'pending' | 'in_progress' | 'completed'
export type TaskPriority = 'low' | 'medium' | 'high'

export interface Task {
  id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  created_at: string
  updated_at: string
}

export interface TaskCreate {
  title: string
  description?: string
  status?: TaskStatus
  priority?: TaskPriority
}

export interface TaskPatch {
  title?: string
  description?: string | null
  status?: TaskStatus
  priority?: TaskPriority
}

export interface TaskListResponse {
  tasks: Task[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface TaskListParams {
  status?: TaskStatus
  priority?: TaskPriority
  page?: number
  page_size?: number
  sort_by?: 'created_at' | 'updated_at' | 'priority'
  sort_order?: 'asc' | 'desc'
}
