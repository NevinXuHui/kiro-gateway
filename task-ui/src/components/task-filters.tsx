import { Button } from '@/components/ui/button'
import type { TaskStatus, TaskPriority } from '@/types/task'

interface TaskFiltersProps {
  status: TaskStatus | undefined
  priority: TaskPriority | undefined
  sortBy: string
  sortOrder: string
  onStatusChange: (v: TaskStatus | undefined) => void
  onPriorityChange: (v: TaskPriority | undefined) => void
  onSortByChange: (v: string) => void
  onSortOrderChange: (v: string) => void
}

const statuses: { value: TaskStatus; label: string }[] = [
  { value: 'pending', label: '待处理' },
  { value: 'in_progress', label: '进行中' },
  { value: 'completed', label: '已完成' },
]

const priorities: { value: TaskPriority; label: string }[] = [
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
]

export function TaskFilters({
  status, priority, sortBy, sortOrder,
  onStatusChange, onPriorityChange, onSortByChange, onSortOrderChange,
}: TaskFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* 状态过滤 */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-muted-foreground mr-1">状态:</span>
        <Button
          variant={status === undefined ? 'default' : 'outline'}
          size="sm"
          onClick={() => onStatusChange(undefined)}
        >
          全部
        </Button>
        {statuses.map((s) => (
          <Button
            key={s.value}
            variant={status === s.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => onStatusChange(s.value)}
          >
            {s.label}
          </Button>
        ))}
      </div>

      <div className="h-6 w-px bg-border mx-1 hidden sm:block" />

      {/* 优先级过滤 */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-muted-foreground mr-1">优先级:</span>
        <Button
          variant={priority === undefined ? 'default' : 'outline'}
          size="sm"
          onClick={() => onPriorityChange(undefined)}
        >
          全部
        </Button>
        {priorities.map((p) => (
          <Button
            key={p.value}
            variant={priority === p.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => onPriorityChange(p.value)}
          >
            {p.label}
          </Button>
        ))}
      </div>

      <div className="h-6 w-px bg-border mx-1 hidden sm:block" />

      {/* 排序 */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-muted-foreground mr-1">排序:</span>
        <select
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          value={sortBy}
          onChange={(e) => onSortByChange(e.target.value)}
        >
          <option value="created_at">创建时间</option>
          <option value="updated_at">更新时间</option>
          <option value="priority">优先级</option>
        </select>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onSortOrderChange(sortOrder === 'desc' ? 'asc' : 'desc')}
        >
          {sortOrder === 'desc' ? '↓' : '↑'}
        </Button>
      </div>
    </div>
  )
}
