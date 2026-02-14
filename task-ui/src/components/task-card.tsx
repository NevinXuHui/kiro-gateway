import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Pencil, Trash2, Clock, CheckCircle2, Loader2 } from 'lucide-react'
import type { Task, TaskStatus } from '@/types/task'

const statusConfig: Record<TaskStatus, { label: string; variant: 'default' | 'warning' | 'success'; icon: typeof Clock }> = {
  pending: { label: '待处理', variant: 'default', icon: Clock },
  in_progress: { label: '进行中', variant: 'warning', icon: Loader2 },
  completed: { label: '已完成', variant: 'success', icon: CheckCircle2 },
}

const priorityConfig = {
  low: { label: '低', className: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300' },
  medium: { label: '中', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' },
  high: { label: '高', className: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' },
}

interface TaskCardProps {
  task: Task
  onEdit: (task: Task) => void
  onDelete: (task: Task) => void
  onStatusChange: (task: Task, status: TaskStatus) => void
}

const nextStatus: Record<TaskStatus, TaskStatus> = {
  pending: 'in_progress',
  in_progress: 'completed',
  completed: 'pending',
}

export function TaskCard({ task, onEdit, onDelete, onStatusChange }: TaskCardProps) {
  const status = statusConfig[task.status]
  const priority = priorityConfig[task.priority]
  const StatusIcon = status.icon

  return (
    <Card className="group hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-base leading-tight line-clamp-2">{task.title}</h3>
          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(task)}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => onDelete(task)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {task.description && (
          <p className="text-sm text-muted-foreground line-clamp-3">{task.description}</p>
        )}
        <div className="flex items-center gap-2 flex-wrap">
          <Badge
            variant={status.variant}
            className="cursor-pointer select-none"
            onClick={() => onStatusChange(task, nextStatus[task.status])}
          >
            <StatusIcon className="h-3 w-3 mr-1" />
            {status.label}
          </Badge>
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${priority.className}`}>
            {priority.label}优先级
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          {new Date(task.created_at).toLocaleString('zh-CN')}
        </p>
      </CardContent>
    </Card>
  )
}
