import { useState } from 'react'
import { Plus, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { TaskCard } from '@/components/task-card'
import { TaskDialog } from '@/components/task-dialog'
import { TaskFilters } from '@/components/task-filters'
import { useTasks, useCreateTask, useUpdateTask, useDeleteTask } from '@/hooks/use-tasks'
import type { Task, TaskStatus, TaskPriority, TaskCreate, TaskPatch } from '@/types/task'

export function TaskList() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<TaskStatus | undefined>()
  const [priority, setPriority] = useState<TaskPriority | undefined>()
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null)

  const { data, isLoading } = useTasks({ status, priority, page, page_size: 12, sort_by: sortBy as 'created_at', sort_order: sortOrder as 'asc' })
  const createMutation = useCreateTask()
  const updateMutation = useUpdateTask()
  const deleteMutation = useDeleteTask()

  const handleCreate = () => {
    setEditingTask(null)
    setDialogOpen(true)
  }

  const handleEdit = (task: Task) => {
    setEditingTask(task)
    setDialogOpen(true)
  }

  const handleSubmit = (formData: TaskCreate | TaskPatch) => {
    if (editingTask) {
      updateMutation.mutate(
        { id: editingTask.id, data: formData as TaskPatch },
        {
          onSuccess: () => { toast.success('任务已更新'); setDialogOpen(false) },
          onError: () => toast.error('更新失败'),
        }
      )
    } else {
      createMutation.mutate(formData as TaskCreate, {
        onSuccess: () => { toast.success('任务已创建'); setDialogOpen(false) },
        onError: () => toast.error('创建失败'),
      })
    }
  }

  const handleStatusChange = (task: Task, newStatus: TaskStatus) => {
    updateMutation.mutate(
      { id: task.id, data: { status: newStatus } },
      { onSuccess: () => toast.success(`状态已更新为 ${newStatus}`) }
    )
  }

  const confirmDelete = () => {
    if (!deleteTarget) return
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => { toast.success('任务已删除'); setDeleteTarget(null) },
      onError: () => toast.error('删除失败'),
    })
  }

  return (
    <div className="space-y-6">
      {/* 工具栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <TaskFilters
          status={status} priority={priority} sortBy={sortBy} sortOrder={sortOrder}
          onStatusChange={(v) => { setStatus(v); setPage(1) }}
          onPriorityChange={(v) => { setPriority(v); setPage(1) }}
          onSortByChange={setSortBy}
          onSortOrderChange={setSortOrder}
        />
        <Button onClick={handleCreate} className="shrink-0">
          <Plus className="h-4 w-4" /> 新建任务
        </Button>
      </div>

      {/* 任务网格 */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : !data?.tasks.length ? (
        <div className="text-center py-12 text-muted-foreground">
          暂无任务，点击「新建任务」开始
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onEdit={handleEdit}
              onDelete={setDeleteTarget}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}

      {/* 分页 */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
          <span className="text-sm text-muted-foreground">{page} / {data.total_pages}（共 {data.total} 条）</span>
          <Button variant="outline" size="sm" disabled={page >= data.total_pages} onClick={() => setPage(page + 1)}>下一页</Button>
        </div>
      )}

      {/* 创建/编辑 Dialog */}
      <TaskDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        task={editingTask}
        onSubmit={handleSubmit}
        loading={createMutation.isPending || updateMutation.isPending}
      />

      {/* 删除确认 Dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">确定要删除任务「{deleteTarget?.title}」吗？此操作不可撤销。</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>取消</Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleteMutation.isPending}>
              {deleteMutation.isPending ? '删除中...' : '删除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
