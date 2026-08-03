import { ref } from 'vue'

interface LogEntry {
  user: string
  action: string
  time: string
  status: 'success' | 'warning' | 'info'
}

const MAX_LOGS = 20

const logs = ref<LogEntry[]>([
  { user: '系统', action: '系统就绪，开始监控工单状态', time: _relativeTime(new Date()), status: 'info' },
])

function _relativeTime(date: Date): string {
  const diff = Date.now() - date.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

/** 向操作日志中添加一条记录 */
export function pushLog(user: string, action: string, status: 'success' | 'warning' | 'info' = 'success') {
  logs.value.unshift({
    user,
    action,
    time: _relativeTime(new Date()),
    status,
  })
  if (logs.value.length > MAX_LOGS) {
    logs.value = logs.value.slice(0, MAX_LOGS)
  }
}

export function useActivityLog() {
  return { logs }
}
