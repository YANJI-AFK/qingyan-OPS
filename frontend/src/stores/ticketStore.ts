import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

interface Ticket {
  id: string
  title: string
  status: string
  priority: string
  assignee: string
  create_time: string
}

export const useTicketStore = defineStore('ticket', () => {
  // ========== 状态 ==========
  const tickets = ref<Ticket[]>([])
  const loading = ref(false)

  // ========== 计算属性 ==========
  const stat = computed(() => {
    const list = tickets.value
    const total = list.length
    const done = list.filter(t => t.status === '已完成').length
    const pending = list.filter(t => t.status === '未完成').length
    const high = list.filter(t => t.priority === '高').length
    return { total, pending, high, done }
  })

  // 高优先级未完成工单列表（供待办预警使用）
  const urgentTickets = computed(() =>
    tickets.value.filter(t => t.priority === '高')
  )

  // ========== 方法 ==========
  async function fetchTickets() {
    loading.value = true
    try {
      const res = await axios.get<Ticket[]>('http://127.0.0.1:5000/api/tickets')
      tickets.value = res.data || []
    } catch (err) {
      console.warn('[TicketStore] 接口不可用', err)
      tickets.value = []
    } finally {
      loading.value = false
    }
  }

  return { tickets, stat, urgentTickets, loading, fetchTickets }
})
