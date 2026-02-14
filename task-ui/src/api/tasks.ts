import axios from 'axios'
import { storage } from '@/lib/storage'
import type { Task, TaskCreate, TaskPatch, TaskListResponse, TaskListParams } from '@/types/task'

const api = axios.create({
  baseURL: '/v1/tasks',
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器：自动添加 Authorization header
api.interceptors.request.use((config) => {
  const apiKey = storage.getApiKey()
  if (apiKey) {
    config.headers['Authorization'] = `Bearer ${apiKey}`
  }
  return config
})

export async function getTasks(params?: TaskListParams): Promise<TaskListResponse> {
  const { data } = await api.get<TaskListResponse>('', { params })
  return data
}

export async function getTask(id: string): Promise<Task> {
  const { data } = await api.get<Task>(`/${id}`)
  return data
}

export async function createTask(task: TaskCreate): Promise<Task> {
  const { data } = await api.post<Task>('', task)
  return data
}

export async function updateTask(id: string, task: TaskPatch): Promise<Task> {
  const { data } = await api.patch<Task>(`/${id}`, task)
  return data
}

export async function deleteTask(id: string): Promise<void> {
  await api.delete(`/${id}`)
}
