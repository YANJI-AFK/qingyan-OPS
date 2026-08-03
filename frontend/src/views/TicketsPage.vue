<script setup lang="ts">
/**
 * TicketsPage.vue — 工单列表管理页（紧凑控制台 + 表格 + 右侧抽屉详情）
 * 1. 顶部紧凑控制台：状态 / 优先级 / 负责人 / 关键词 / 刷新
 * 2. 主体表格：分页、复选、操作栏（查看详情 / 编辑）
 * 3. 右侧内嵌抽屉：基础信息 + 流转时间轴 + 底部快捷操作
 * 4. 路由参数联动：HomePage 跳过来时根据 ?filterStatus 自动同步筛选器
 */
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { pushLog } from '../stores/activityLog'

const route = useRoute()
const API = 'http://127.0.0.1:5000'

// ========== 数据 ==========
interface Ticket {
  id: string
  title: string
  status: string
  priority: string
  assignee: string
  create_time: string
  description?: string
}
const tickets = ref<Ticket[]>([])
const total = ref(0)
const currentPage = ref(1)
const loading = ref(false)
const searchKeyword = ref('')
const filterStatus = ref('全部')
const filterPriority = ref('全部')
const filterAssignee = ref('全部')
const filterDate = ref('')
const filterDateStart = ref('')
const filterDateEnd = ref('')
const dateMode = ref<'single' | 'range'>('single')
const viewportHeight = ref(window.innerHeight)

// Toast 提示（替代浏览器 alert）
const toastMessage = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null
function showToast(msg: string) {
  toastMessage.value = msg
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMessage.value = '' }, 2000)
}

// 动态计算每页行数：填满表格区域，不固定数量
function calcPageSize(): number {
  const h = viewportHeight.value
  // h - topnav(60) - pagePadding上下(48) - controlBar(56) - wrapperPadding上下(40) - tableHeader(44) - pagination(50)
  // 乘以0.9补偿全局 zoom:0.9，使行数计算与实际缩放后的可用空间匹配
  const rowH = 52 * 0.85 // 每行缩放后约47px
  const available = (h - 60 - 48 - 56 - 40 - 44 - 50) * 0.85
  return Math.max(5, Math.floor(available / rowH))
}
const pageSize = ref(calcPageSize())
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

// ========== 抽屉详情 ==========
const showDrawer = ref(false)
const currentTicket = ref<Ticket | null>(null)

// ========== 人员列表（供新建工单使用）==========
const staffNames = ref<string[]>([])

async function fetchStaffNames() {
  try {
    const res = await axios.get(`${API}/api/staff/list`)
    staffNames.value = (res.data || []).filter((s: any) => s.status === '启用').map((s: any) => s.name)
  } catch { /* ignore */ }
}

// ========== 新建工单 ==========
const createModalVisible = ref(false)
const createForm = ref({ title: '', priority: '中', assignee: '', description: '' })
const createLoading = ref(false)
const createError = ref('')

function openCreateModal() {
  createForm.value = { title: '', priority: '中', assignee: staffNames.value[0] || '', description: '' }
  createError.value = ''
  createModalVisible.value = true
  // 异步加载配置中的默认优先级
  axios.get(`${API}/api/config/params`).then(res => {
    const dp = res.data?.ticket_default_priority
    if (dp && ['高','中','低'].includes(dp)) {
      createForm.value.priority = dp
    }
  }).catch(() => {})
}

async function doCreateTicket() {
  if (!createForm.value.title.trim()) { createError.value = '请输入工单标题'; return }
  if (!createForm.value.assignee) { createError.value = '请选择负责人'; return }
  createLoading.value = true
  createError.value = ''
  try {
    const res = await axios.post(`${API}/api/tickets/create`, createForm.value)
    if (!res.data.ok) { createError.value = res.data.reason || '创建失败'; return }
    pushLog('当前用户', `创建了工单「${createForm.value.title}」`, 'success')
    createModalVisible.value = false
    fetchTickets()
  } catch (e: any) {
    createError.value = e?.response?.data?.reason || '创建失败'
  } finally {
    createLoading.value = false
  }
}

// ========== 删除工单 ==========
const deleteConfirmVisible = ref(false)
const deleteTargetId = ref('')
const deleteLoading = ref(false)
const deleteError = ref('')

function openDeleteConfirm(ticket: Ticket) {
  deleteTargetId.value = ticket.id
  deleteError.value = ''
  deleteConfirmVisible.value = true
}

function handleDeleteClick(ticket: Ticket) {
  if (ticket.status === '进行中') {
    showToast('进行中的工单不可删除')
    return
  }
  openDeleteConfirm(ticket)
}

async function doDeleteTicket() {
  const tid = deleteTargetId.value
  deleteLoading.value = true
  deleteError.value = ''
  try {
    const res = await axios.post(`${API}/api/tickets/${tid}/delete`)
    if (!res.data.ok) { deleteError.value = res.data.reason || '删除失败'; return }
    pushLog('当前用户', `删除了工单 ${deleteTargetId.value}`, 'warning')
    deleteConfirmVisible.value = false
    fetchTickets()
  } catch (e: any) {
    deleteError.value = e?.response?.data?.reason || '删除失败'
  } finally {
    deleteLoading.value = false
  }
}

// ========== 指派工单 ==========
interface Candidate {
  name: string
  role?: string
  high_priority_count: number
  total_pending: number
  score: number
  recommended?: boolean
}
const assignModalVisible = ref(false)
const assignCandidates = ref<Candidate[]>([])
const assignTicketId = ref('')
const assignCurrentAssignee = ref('')
const assignSelected = ref('')
const assignLoading = ref(false)
const assignError = ref('')

async function openAssignModal(ticket: Ticket) {
  const tid = ticket.id
  assignTicketId.value = ticket.id
  assignCurrentAssignee.value = ticket.assignee
  assignSelected.value = ''
  assignError.value = ''
  assignCandidates.value = []
  assignModalVisible.value = true
  assignLoading.value = true
  try {
    const res = await axios.get(`${API}/api/tickets/${tid}/candidates`)
    const raw = res.data.data || res.data.candidates || []
    const list: Candidate[] = raw.sort(
      (a: any, b: any) => (b.score || 0) - (a.score || 0),
    )
    assignCandidates.value = list
    if (list.length > 0) {
      assignSelected.value = list[0].name
    }
  } catch (e: any) {
    assignError.value = e?.response?.data?.reason || '获取候选列表失败'
  } finally {
    assignLoading.value = false
  }
}

async function doAssignTicket() {
  if (!assignSelected.value) { assignError.value = '请选择负责人'; return }
  const tid = assignTicketId.value
  assignLoading.value = true
  assignError.value = ''
  try {
    const res = await axios.post(`${API}/api/tickets/${tid}/assign`, { assignee: assignSelected.value })
    if (!res.data.ok) { assignError.value = res.data.reason || '指派失败'; return }
    pushLog('当前用户', `将工单 ${assignTicketId.value} 指派给 ${assignSelected.value}`, 'success')
    assignModalVisible.value = false
    fetchTickets()
  } catch (e: any) {
    assignError.value = e?.response?.data?.reason || '指派失败'
  } finally {
    assignLoading.value = false
  }
}

// ========== 工单流转历史 ==========
const ticketHistory = ref<any[]>([])
const historyLoading = ref(false)

async function fetchTicketHistory(tid: string) {
  historyLoading.value = true
  try {
    const res = await axios.get(`${API}/api/tickets/${tid}/history`)
    ticketHistory.value = res.data.history || res.data || []
  } catch {
    ticketHistory.value = []
  } finally {
    historyLoading.value = false
  }
}

function getHistoryDotClass(action: string) {
  if (!action) return 'normal'
  if (action.includes('创建')) return 'success'
  if (action.includes('变更') || action.includes('修改')) return 'warning'
  return 'normal'
}

function getHistoryActionText(h: any) {
  return h.action || ''
}

// ========== 编辑工单（状态+优先级） ==========
const editModalVisible = ref(false)
const editForm = ref({ id: '', title: '', status: '', priority: '', description: '' })
const editLoading = ref(false)
const editError = ref('')

function openEditModal(ticket: Ticket) {
  editForm.value = {
    id: ticket.id,
    title: ticket.title,
    status: ticket.status,
    priority: ticket.priority,
    description: ticket.description || '',
  }
  editError.value = ''
  editModalVisible.value = true
}

async function doEditTicket() {
  editLoading.value = true
  editError.value = ''
  try {
    const res = await axios.post(`${API}/api/tickets/update`, {
      id: editForm.value.id,
      status: editForm.value.status,
      priority: editForm.value.priority,
      description: editForm.value.description,
    })
    if (!res.data.success) { editError.value = res.data.error || '编辑失败'; return }
    pushLog('当前用户', `修改了工单 ${editForm.value.id}`, 'warning')
    editModalVisible.value = false
    fetchTickets()
  } catch (e: any) {
    editError.value = e?.response?.data?.error || '编辑失败'
  } finally {
    editLoading.value = false
  }
}

// ========== 工具函数 ==========
const getStatusColor = (s: string) =>
  ({ '已完成': '#10b981', '进行中': '#3b82f6', '未完成': '#f59e0b' }[s] || '#94a3b8')
const getPriorityClass = (p: string) =>
  ({ '高': 'p-high', '中': 'p-mid', '低': 'p-low' }[p] || 'p-low')
const getAssigneeInitial = (name: string) => (name ? name.charAt(0) : '?')
const getAvatarColor = (name: string) => {
  const colors = ['#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#f59e0b', '#ef4444']
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return colors[Math.abs(hash) % colors.length]
}

// ========== 数据获取 ==========
async function fetchTickets() {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      limit: pageSize.value,
    }
    if (searchKeyword.value.trim()) params.keyword = searchKeyword.value.trim()
    if (filterStatus.value !== '全部') params.status = filterStatus.value
    if (filterPriority.value !== '全部') params.priority = filterPriority.value
    if (filterAssignee.value !== '全部') params.assignee = filterAssignee.value
    if (dateMode.value === 'single' && filterDate.value) {
      params.date = filterDate.value
    } else if (dateMode.value === 'range') {
      if (filterDateStart.value) params.date_start = filterDateStart.value
      if (filterDateEnd.value) params.date_end = filterDateEnd.value
    }

    const res = await axios.get(`${API}/api/tickets/page`, { params })
    tickets.value = res.data.data || []
    total.value = res.data.total || 0
  } catch (e) {
    // 降级：Mock 数据兜底
    tickets.value = [
      { id: 'TKT-20260722-0001', title: '数据库连接池耗尽导致服务不可用', status: '未完成', priority: '高', assignee: '张三', create_time: '2026-07-22 10:24:00' },
      { id: 'TKT-20260722-0002', title: '前端控制台报跨域 CORS 拦截错误', status: '进行中', priority: '中', assignee: '王五', create_time: '2026-07-22 09:15:33' },
      { id: 'TKT-20260722-0003', title: '数字人语音合成模块加载超时', status: '未完成', priority: '高', assignee: '李四', create_time: '2026-07-22 08:40:12' },
      { id: 'TKT-20260721-0001', title: '新增用户管理页面的权限控制', status: '已完成', priority: '低', assignee: '赵六', create_time: '2026-07-21 16:20:00' },
      { id: 'TKT-20260721-0002', title: '服务器 Node-07 磁盘空间不足预警', status: '进行中', priority: '高', assignee: '张三', create_time: '2026-07-21 14:05:45' },
    ]
    total.value = tickets.value.length
  } finally {
    loading.value = false
  }
}

// 筛选条件变化 → 重置到第 1 页 + 重新拉取
function onFilterChange() {
  currentPage.value = 1
  fetchTickets()
}

// 格式化 ISO 日期为 例:2000-01-01 风格的展示
function formatDateDisplay(iso: string): string {
  if (!iso) return ''
  // iso 格式为 yyyy-mm-dd
  return iso.replace(/-/g, '-')
}

// 当日期值变化时进行校验
function onDateChange(field: 'single' | 'start' | 'end') {
  if (dateMode.value === 'single') {
    if (field !== 'single') return
    onFilterChange()
    return
  }
  // 时间段模式
  if (filterDateStart.value && filterDateEnd.value) {
    if (filterDateEnd.value < filterDateStart.value) {
      showToast('结束日期不能早于开始日期')
      if (field === 'end') filterDateEnd.value = ''
      else filterDateStart.value = ''
      return
    }
  }
  onFilterChange()
}
function onPageChange(p: number) {
  if (p < 1 || p > totalPages.value) return
  currentPage.value = p
  fetchTickets()
}

// 快速输入页码跳转
const pageInput = ref('')
function goToPage() {
  const p = parseInt(pageInput.value)
  if (!isNaN(p) && p >= 1 && p <= totalPages.value) {
    onPageChange(p)
  }
  pageInput.value = ''
}

// 打开详情弹窗
function openDetailDrawer(t: Ticket) {
  currentTicket.value = t
  showDrawer.value = true
}

// ========== 路由 query 联动（核心）==========
watch(
  () => route.query.filterStatus,
  (newVal) => {
    if (newVal && typeof newVal === 'string') {
      const valid = ['全部', '未完成', '进行中', '已完成']
      if (valid.includes(newVal)) {
        filterStatus.value = newVal
        currentPage.value = 1
        fetchTickets()
      }
    }
  },
  { immediate: true },
)

watch(
  () => route.query.filterPriority,
  (newVal) => {
    if (newVal && typeof newVal === 'string') {
      const valid = ['全部', '高', '中', '低']
      if (valid.includes(newVal)) {
        filterPriority.value = newVal
        currentPage.value = 1
        fetchTickets()
      }
    }
  },
  { immediate: true },
)

// ========== 窗口大小变化时动态调整行数 ==========
let resizeTimer: ReturnType<typeof setTimeout> | null = null
function onWindowResize() {
  viewportHeight.value = window.innerHeight
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    const newSize = calcPageSize()
    if (newSize !== pageSize.value) {
      pageSize.value = newSize
      fetchTickets()
    }
  }, 200)
}

onMounted(() => {
  fetchTickets()
  fetchStaffNames()
  window.addEventListener('resize', onWindowResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})
</script>

<template>
  <div class="tickets-page">
    <!-- 1. 顶部控制台 -->
    <div class="control-bar">
      <div class="filters">
        <!-- 明确标注筛选类别，且保持 value="全部" 逻辑不破坏 -->
        <select class="filter-select" v-model="filterStatus" @change="onFilterChange">
          <option value="全部">全部状态</option>
          <option value="未完成">未完成</option>
          <option value="进行中">进行中</option>
          <option value="已完成">已完成</option>
        </select>
        <select class="filter-select" v-model="filterPriority" @change="onFilterChange">
          <option value="全部">全部优先级</option>
          <option value="高">高</option>
          <option value="中">中</option>
          <option value="低">低</option>
        </select>
        <select class="filter-select" v-model="filterAssignee" @change="onFilterChange">
          <option value="全部">全部负责人</option>
          <option value="张三">张三</option>
          <option value="李四">李四</option>
          <option value="王五">王五</option>
          <option value="赵六">赵六</option>
        </select>

        <!-- 日期筛选 -->
        <div class="date-filter-group">
          <select class="filter-select date-mode-select" v-model="dateMode">
            <option value="single">单日</option>
            <option value="range">时间段</option>
          </select>
          <template v-if="dateMode === 'single'">
            <div class="date-input-wrap">
              <input type="date" class="filter-select date-input" :class="{ 'is-empty': !filterDate }" v-model="filterDate" @change="onDateChange('single')" />
              <span v-if="!filterDate" class="date-placeholder">例:2000-01-01</span>
              <span v-else class="date-display">{{ filterDate }}</span>
            </div>
          </template>
          <template v-else>
            <div class="date-input-wrap">
              <input type="date" class="filter-select date-input" :class="{ 'is-empty': !filterDateStart }" v-model="filterDateStart" :max="filterDateEnd || undefined" @change="onDateChange('start')" />
              <span v-if="!filterDateStart" class="date-placeholder">例:2000-01-01</span>
              <span v-else class="date-display">{{ filterDateStart }}</span>
            </div>
            <span class="date-sep">~</span>
            <div class="date-input-wrap">
              <input type="date" class="filter-select date-input" :class="{ 'is-empty': !filterDateEnd }" v-model="filterDateEnd" :min="filterDateStart || undefined" @change="onDateChange('end')" />
              <span v-if="!filterDateEnd" class="date-placeholder">例:2000-12-31</span>
              <span v-else class="date-display">{{ filterDateEnd }}</span>
            </div>
          </template>
        </div>
        
        <!-- 带有放大镜的搜索框 -->
        <div class="search-box">
          <input
            class="search-input"
            v-model="searchKeyword"
            placeholder="输入工单标题关键词..."
            @keyup.enter="onFilterChange"
          />
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" @click="fetchTickets">刷新列表</button>
        <button class="btn btn-success" @click="openCreateModal">+ 新建工单</button>
      </div>
    </div>

    <!-- 2. 主体数据表格 (使用 flex 占满全屏，分页顺底) -->
    <div class="table-wrapper">
      <div class="table-scroll-area">
        <div v-if="loading" class="loading-tip">数据加载中…</div>
        <table class="main-table" v-else>
          <thead>
            <tr>
              <th style="width: 40px;"><input type="checkbox" /></th>
              <th style="width: 150px;">工单编号</th>
              <th>故障标题</th>
              <th style="width: 90px;">优先级</th>
              <th style="width: 100px;">状态</th>
              <th style="width: 130px;">处理人</th>
              <th style="width: 180px;">创建时间</th>
              <th style="width: 220px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ticket in tickets" :key="ticket.id">
              <td><input type="checkbox" /></td>
              <!-- 工单编号字号变大 -->
              <td><span class="id-font">{{ ticket.id }}</span></td>
              <!-- 故障标题字号变大 -->
              <td class="title-font">{{ ticket.title }}</td>
              <td><span class="priority-tag" :class="getPriorityClass(ticket.priority)">{{ ticket.priority }}</span></td>
              <td>
                <span class="status-tag" :style="{ color: getStatusColor(ticket.status), borderColor: getStatusColor(ticket.status) }">
                  {{ ticket.status }}
                </span>
              </td>
              <td>
                <span class="assignee-name">{{ ticket.assignee }}</span>
              </td>
              <td class="time-font">{{ ticket.create_time }}</td>
              <td>
                <div class="action-icons">
                  <button class="icon-btn" title="查看详情" @click="openDetailDrawer(ticket)">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  </button>
                  <button class="icon-btn" title="编辑" @click="openEditModal(ticket)">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                  </button>
                  <button class="icon-btn" :class="{ 'icon-btn-danger': ticket.status !== '进行中', 'icon-btn-disabled': ticket.status === '进行中' }" :title="ticket.status === '进行中' ? '进行中的工单不可删除' : '删除'" @click="handleDeleteClick(ticket)">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      <line x1="10" y1="11" x2="10" y2="17"/>
                      <line x1="14" y1="11" x2="14" y2="17"/>
                    </svg>
                  </button>
                  <button class="icon-btn" title="指派" @click="openAssignModal(ticket)">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="8.5" cy="7" r="4"/>
                      <polyline points="17 8 21 12 17 16"/>
                      <line x1="21" y1="12" x2="9" y2="12"/>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!loading && tickets.length === 0">
              <td colspan="8" class="empty-row">没有符合条件的工单</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页沉底展示 -->
      <div v-if="total > 0" class="pagination">
        <span class="page-info">共 <b>{{ total }}</b> 条 · 第 {{ currentPage }} / {{ totalPages }} 页</span>
        <div class="page-controls">
          <button class="page-btn" :disabled="currentPage === 1" @click="onPageChange(1)" title="首页">«</button>
          <button class="page-btn" :disabled="currentPage <= 1" @click="onPageChange(currentPage - 1)">上一页</button>
          <button class="page-btn" :disabled="currentPage >= totalPages" @click="onPageChange(currentPage + 1)">下一页</button>
          <button class="page-btn" :disabled="currentPage === totalPages" @click="onPageChange(totalPages)" title="末页">»</button>
          <div class="page-jump">
            跳转
            <input v-model="pageInput" @keyup.enter="goToPage" type="number" min="1" :max="totalPages" class="page-input" />
            页
          </div>
        </div>
      </div>
    </div>

    <!-- 3. 工单详情弹窗（居中显示） -->
    <div class="modal-overlay" v-if="showDrawer" @click.self="showDrawer = false">
      <div class="modal-box detail-modal">
        <div class="detail-header">
          <div class="dh-left">
            <div class="dh-id-row">
              <span class="dh-id">{{ currentTicket?.id }}</span>
              <span class="dh-status" :style="{ background: getStatusColor(currentTicket?.status || '') }">{{ currentTicket?.status }}</span>
            </div>
          </div>
          <button class="drawer-close" @click="showDrawer = false">✕</button>
        </div>

        <div class="detail-body">
          <div class="detail-grid">
            <div class="dg-item dg-full">
              <span class="dg-label">标题</span>
              <span class="dg-val dg-bold">{{ currentTicket?.title }}</span>
            </div>
            <div class="dg-item">
              <span class="dg-label">优先级</span>
              <span class="dg-val"><span :class="getPriorityClass(currentTicket?.priority || '')" class="priority-tag">{{ currentTicket?.priority }}</span></span>
            </div>
            <div class="dg-item">
              <span class="dg-label">负责人</span>
              <span class="dg-val">{{ currentTicket?.assignee }}</span>
            </div>
            <div class="dg-item">
              <span class="dg-label">创建时间</span>
              <span class="dg-val">{{ currentTicket?.create_time }}</span>
            </div>
            <div class="dg-item">
              <!-- 占位保持网格对齐 --></div>
            <div class="dg-item dg-full">
              <span class="dg-label">内容描述</span>
              <span class="dg-val">{{ currentTicket?.description || '暂无描述' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 4. 新建工单模态框 -->
    <div class="modal-overlay" v-if="createModalVisible" @click.self="createModalVisible = false">
      <div class="modal-box">
        <h3>新建工单</h3>
        <div class="form-field">
          <label>工单标题 <span class="required">*</span></label>
          <input v-model="createForm.title" placeholder="请输入工单标题" class="text-input" @keyup.enter="doCreateTicket" />
        </div>
        <div class="form-row">
          <div class="form-field">
            <label>优先级</label>
            <select v-model="createForm.priority" class="text-input">
              <option value="高">高</option>
              <option value="中">中</option>
              <option value="低">低</option>
            </select>
          </div>
          <div class="form-field">
            <label>负责人 <span class="required">*</span></label>
            <select v-model="createForm.assignee" class="text-input">
              <option value="" disabled>请选择负责人</option>
              <option v-for="name in staffNames" :key="name" :value="name">{{ name }}</option>
            </select>
          </div>
        </div>
        <div class="form-field">
          <label>内容描述</label>
          <textarea v-model="createForm.description" placeholder="请输入工单详细描述（选填）" class="text-input text-area" rows="3"></textarea>
        </div>
        <p v-if="createError" class="form-error">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="createModalVisible = false">取消</button>
          <button class="btn-primary" @click="doCreateTicket" :disabled="createLoading">{{ createLoading ? '创建中...' : '确认创建' }}</button>
        </div>
      </div>
    </div>

    <!-- 5. 编辑工单模态框 -->
    <div class="modal-overlay" v-if="editModalVisible" @click.self="editModalVisible = false">
      <div class="modal-box edit-modal">
        <div class="edit-header">
          <h3 class="edit-heading">编辑工单</h3>
          <span class="edit-tkt">TKT-{{ editForm.id.split('-').slice(1).join('-') }}</span>
        </div>

        <div class="edit-grid">
          <div class="eg-item eg-full">
            <label class="eg-label">工单标题</label>
            <span class="eg-val eg-title-text">{{ editForm.title }}</span>
          </div>
          <div class="eg-item">
            <label class="eg-label">状态</label>
            <div class="eg-select-wrap">
              <select v-model="editForm.status" class="eg-select">
                <option value="未完成">未完成</option>
                <option value="进行中">进行中</option>
                <option value="已完成">已完成</option>
              </select>
              <svg class="eg-select-arrow" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
          </div>
          <div class="eg-item">
            <label class="eg-label">优先级</label>
            <div class="eg-select-wrap">
              <select v-model="editForm.priority" class="eg-select">
                <option value="高">高</option>
                <option value="中">中</option>
                <option value="低">低</option>
              </select>
              <svg class="eg-select-arrow" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
          </div>
          <div class="eg-item dg-full" style="grid-column: 1 / -1;">
            <label class="eg-label">内容描述</label>
            <textarea v-model="editForm.description" class="text-input text-area" rows="3" placeholder="请输入工单详细描述"></textarea>
          </div>
        </div>
        <p v-if="editError" class="form-error">{{ editError }}</p>
        <div class="edit-actions">
          <button class="eg-btn eg-btn-secondary" @click="editModalVisible = false">取消</button>
          <button class="eg-btn eg-btn-primary" @click="doEditTicket" :disabled="editLoading">{{ editLoading ? '保存中...' : '保存修改' }}</button>
        </div>
      </div>
    </div>

    <!-- 6. 删除确认弹窗 -->
    <div class="modal-overlay" v-if="deleteConfirmVisible" @click.self="deleteConfirmVisible = false">
      <div class="modal-box modal-box-sm">
        <h3>确认删除</h3>
        <p class="delete-confirm-text">确定删除工单 <strong>{{ deleteTargetId }}</strong> 吗？此操作不可恢复</p>
        <p v-if="deleteError" class="form-error">{{ deleteError }}</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="deleteConfirmVisible = false">取消</button>
          <button class="btn-danger" @click="doDeleteTicket" :disabled="deleteLoading">{{ deleteLoading ? '删除中...' : '确认删除' }}</button>
        </div>
      </div>
    </div>

    <!-- 7. 指派模态框 -->
    <div class="modal-overlay" v-if="assignModalVisible" @click.self="assignModalVisible = false">
      <div class="modal-box">
        <h3>指派工单 <span class="assign-tkt-id">{{ assignTicketId }}</span></h3>
        <p class="assign-current-info">当前负责人：<strong>{{ assignCurrentAssignee || '无' }}</strong></p>
        <div class="candidate-list" v-if="!assignLoading">
          <div
            v-for="c in assignCandidates"
            :key="c.name"
            class="candidate-item"
            :class="{ selected: assignSelected === c.name, recommended: c.recommended }"
            @click="assignSelected = c.name"
          >
            <div class="candidate-info">
              <span class="candidate-name">{{ c.name }}</span>
              <span class="candidate-role">{{ c.role || '' }}</span>
              <span v-if="c.total_pending >= 10" class="warning-badge">忙碌</span>
              <span v-if="c.recommended" class="recommended-badge">推荐</span>
            </div>
            <div class="candidate-stats">
              <span>高优: {{ c.high_priority_count }}</span>
              <span>待处理: {{ c.total_pending }}</span>
            </div>
          </div>
          <p v-if="assignCandidates.length === 0" class="empty-row" style="padding: 20px;">暂无可用候选人</p>
        </div>
        <div v-else class="loading-tip" style="padding: 20px;">加载中...</div>
        <p v-if="assignError" class="form-error">{{ assignError }}</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="assignModalVisible = false">取消</button>
          <button class="btn-primary" @click="doAssignTicket" :disabled="assignLoading || assignCandidates.length === 0">{{ assignLoading ? '指派中...' : '确认指派' }}</button>
        </div>
      </div>
    </div>

    <!-- Toast 提示 -->
    <div class="toast" v-if="toastMessage">{{ toastMessage }}</div>
  </div>
</template>

<style scoped>
.tickets-page { 
  padding: 24px; 
  background: #f1f5f9; 
  height: calc((100vh - 60px) / 0.85); 
  box-sizing: border-box; 
  display: flex; 
  flex-direction: column; 
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}

/* 1. 顶部紧凑控制台 */
.control-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  padding: 16px 24px;
  border-radius: 10px;
  margin-bottom: 16px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
}
.filters { display: flex; gap: 12px; flex: 1; max-width: 900px; align-items: center; }
.filter-select {
  padding: 10px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  background: #fff;
  color: #334155;
  transition: all 0.2s;
}
.filter-select:focus { 
  border-color: #3b82f6; 
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15); 
}

/* 日期筛选 */
.date-filter-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.date-mode-select {
  width: 80px;
  padding: 10px 8px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.date-input-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.date-input {
  width: 140px;
  padding: 10px 32px 10px 10px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  background: #fff;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  color: #334155;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;
  position: relative;
}
.date-input::-webkit-calendar-picker-indicator {
  cursor: pointer;
  opacity: 0.6;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.date-input::-webkit-datetime-edit {
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.date-input::-webkit-datetime-edit-fields-wrapper {
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.date-input:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
  background: #fff;
}
/* 隐藏空的原生日期占位（yyyy/mm/日） */
.date-input.is-empty::-webkit-datetime-edit,
.date-input.is-empty::-webkit-datetime-edit-fields-wrapper,
.date-input.is-empty::-webkit-datetime-edit-text,
.date-input.is-empty::-webkit-datetime-edit-month-field,
.date-input.is-empty::-webkit-datetime-edit-day-field,
.date-input.is-empty::-webkit-datetime-edit-year-field {
  color: transparent;
}
/* 选中日期后也隐藏原生展示文字（用自定义 .date-display 覆盖） */
.date-input:not(.is-empty)::-webkit-datetime-edit,
.date-input:not(.is-empty)::-webkit-datetime-edit-fields-wrapper,
.date-input:not(.is-empty)::-webkit-datetime-edit-text,
.date-input:not(.is-empty)::-webkit-datetime-edit-month-field,
.date-input:not(.is-empty)::-webkit-datetime-edit-day-field,
.date-input:not(.is-empty)::-webkit-datetime-edit-year-field {
  color: transparent;
}
.date-placeholder {
  position: absolute;
  left: 10px;
  right: 50px;
  top: 50%;
  transform: translateY(-50%);
  color: #94a3b8;
  font-size: 14px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  pointer-events: none;
  letter-spacing: 0.5px;
  user-select: none;
  text-align: center;
}
.date-display {
  position: absolute;
  left: 10px;
  right: 50px;
  top: 50%;
  transform: translateY(-50%);
  color: #334155;
  font-size: 14px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  pointer-events: none;
  letter-spacing: 0.5px;
  user-select: none;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.date-sep {
  color: #94a3b8;
  font-size: 14px;
  user-select: none;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}

/* 带有图标的搜索栏结构 */
.search-box {
  position: relative;
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
}
.search-input {
  width: 100%;
  padding: 10px 36px 10px 14px; /* 右侧留白给图标 */
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  background: #fff;
  color: #334155;
  transition: all 0.2s;
  box-sizing: border-box;
}
.search-input:focus {
  border-color: #3b82f6; 
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15); 
}
.search-icon {
  position: absolute;
  right: 12px;
  width: 16px;
  height: 16px;
  color: #94a3b8;
  pointer-events: none; /* 防止遮挡点击 */
}

.actions { display: flex; gap: 12px; }
.btn { 
  padding: 9px 20px; 
  border-radius: 8px; 
  border: 1px solid #cbd5e1; 
  color: #334155; 
  background: #fff;
  cursor: pointer; 
  font-size: 14px; 
  font-weight: 500; 
  transition: all 0.15s; 
}
.btn:hover:not(:disabled) { background: #f8fafc; border-color: #94a3b8; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.btn-primary, .btn.btn-success {
  background: #fff;
  border: 1px solid #cbd5e1;
  color: #334155;
}

/* 2. 主体表格（Flex布局支持高度占满与分页沉底） */
.table-wrapper { 
  flex: 1; 
  background: #fff; 
  border-radius: 10px; 
  padding: 20px 24px; 
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04); 
  display: flex;
  flex-direction: column;
  overflow: hidden; /* 防止整个容器在父级溢出 */
}
.table-scroll-area {
  flex: 1;
  overflow-y: auto; /* 让内部表格可以滚动 */
}
.loading-tip { padding: 60px; text-align: center; color: #64748b; font-size: 15px; }
.main-table { width: 100%; border-collapse: separate; border-spacing: 0; text-align: center; }
.main-table th { 
  padding: 16px; 
  background: #f8fafc; 
  color: #475569; 
  font-weight: 600; 
  font-size: 15px; 
  border-bottom: 2px solid #e2e8f0; 
  position: sticky;
  top: 0;
  z-index: 10;
  vertical-align: middle;
  text-align: center;
}
.main-table td { 
  padding: 16px; 
  border-bottom: 1px solid #f1f5f9; 
  font-size: 14px; 
  color: #334155; 
  vertical-align: middle;
  text-align: center;
}
.main-table tbody tr { transition: background-color 0.2s; }
.main-table tbody tr:hover td { background: #f8fafc; }

/* --- 修改点：工单编号字体 --- */
.id-font { 
  font-family: 'SF Mono', Consolas, 'Courier New', monospace;
  color: #0f172a; 
  font-size: 15px;
  font-weight: 500; 
  letter-spacing: 0.3px;
}
.title-font { 
  color: #0f172a; 
  font-weight: 500;
  font-size: 15px;
}
/* ------------------------ */

.time-font { color: #64748b; font-size: 14px; font-weight: 400; }
.empty-row { padding: 80px !important; text-align: center; color: #94a3b8; font-size: 15px; }

/* 按钮与标签 */
.btn-outline { 
  padding: 6px 14px; 
  border: 1px solid #cbd5e1; 
  border-radius: 6px; 
  background: transparent; 
  cursor: pointer; 
  color: #3b82f6; 
  transition: all 0.2s; 
  font-size: 14px; 
  font-weight: 500;
}
.btn-outline:hover:not(:disabled) { background: #eff6ff; border-color: #93c5fd; }
.btn-outline:disabled { color: #cbd5e1; cursor: not-allowed; }
.btn-outline-small { 
  padding: 6px 14px; 
  border: 1px solid #cbd5e1; 
  border-radius: 6px; 
  background: transparent; 
  cursor: pointer; 
  color: #64748b; 
  font-size: 14px; 
  margin-left: 10px; 
}
.btn-outline-small:hover:not(:disabled) { background: #f8fafc; }
.btn-outline-small:disabled { cursor: not-allowed; }

/* 图标按钮组 */
.action-icons { display: flex; gap: 2px; align-items: center; justify-content: center; }
.icon-btn {
  width: 32px; height: 32px;
  display: inline-flex; align-items: center; justify-content: center;
  border: none; border-radius: 6px;
  background: transparent; color: #94a3b8;
  cursor: pointer; transition: all 0.15s;
}
.icon-btn:hover { background: #f1f5f9; color: #475569; }
.icon-btn-danger:hover { background: #fef2f2; color: #ef4444; }
.icon-btn-disabled { color: #d1d5db; cursor: not-allowed; }
.icon-btn-disabled:hover { background: transparent; color: #d1d5db; }

.status-tag { 
  display: inline-block; 
  padding: 4px 12px; 
  border-radius: 6px; 
  font-size: 13px; 
  font-weight: 600; 
  border: 1px solid; 
  background: #fff; 
}
.priority-tag { 
  display: inline-block;
  padding: 4px 12px; 
  border-radius: 6px; 
  font-size: 13px; 
  font-weight: 600; 
}
.p-high { background: #fef2f2; color: #ef4444; }
.p-mid { background: #fffbeb; color: #f59e0b; }
.p-low { background: #f0fdf4; color: #10b981; }

.assignee-name { color: #1e293b; font-size: 14px; font-weight: 500; }

/* 分页沉底支持 */
.pagination {
  margin-top: auto; /* 保证分页始终推至容器最底部 */
  padding-top: 16px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  border-top: 1px solid #f1f5f9;
}
.page-info { color: #64748b; font-size: 14px; margin-right: auto; }
.page-info b { color: #0f172a; font-size: 15px; }
.page-controls { display: flex; align-items: center; gap: 8px; }
.page-btn {
  min-width: 36px;
  height: 34px;
  padding: 0 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.page-btn:hover:not(:disabled) { border-color: #3b82f6; color: #3b82f6; }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; background: #f8fafc; }
.page-jump {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  color: #64748b;
  font-size: 14px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.page-input {
  width: 56px;
  height: 34px;
  padding: 0 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
  text-align: center;
  font-family: inherit;
  color: #0f172a;
  outline: none;
  transition: border-color 0.2s;
}
.page-input:focus { border-color: #3b82f6; }
.page-input::-webkit-outer-spin-button,
.page-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }

/* 3. 工单详情弹窗（居中 + 亲密性网格） */
.detail-modal { width: 520px; max-width: 90vw; }

/* --- 头部：编号 + 状态 + 关闭 --- */
.detail-header { 
  display: flex; justify-content: space-between; align-items: flex-start;
  padding-bottom: 16px; margin-bottom: 4px;
}
.dh-left { }
.dh-id-row { display: flex; align-items: center; gap: 10px; }
.dh-id { 
  font-family: 'Times New Roman', Times, serif;
  font-size: 15px; color: #0f172a; font-weight: 700; letter-spacing: 0.5px;
}
.dh-status { 
  padding: 3px 12px; border-radius: 4px; color: #fff; font-size: 12px; font-weight: 500;
}

/* --- 网格主体 --- */
.detail-body { }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px 24px; }
.dg-item.dg-full { grid-column: 1 / -1; }

/* 标签：缩小、灰色、贴近内容 */
.dg-label { 
  display: block; font-size: 12px; color: #94a3b8; margin-bottom: 5px; 
  font-weight: 500; letter-spacing: 0.2px;
}
/* 值：正常字号、与上方标签紧贴 */
.dg-val { 
  font-size: 14px; color: #0f172a; line-height: 1.45; font-weight: 500; word-break: break-word; 
}
/* 标题等核心内容加粗 */
.dg-bold { font-weight: 600; font-size: 15px; }

/* 关闭按钮 */
.drawer-close { 
  width: 28px; height: 28px; border: none; background: #f1f5f9;
  border-radius: 6px; cursor: pointer; font-size: 14px; color: #64748b;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  line-height: 1; transition: all 0.15s;
}
.drawer-close:hover { background: #e2e8f0; color: #0f172a; }

/* ====== 编辑工单模态框 ====== */
.edit-modal { width: 520px; max-width: 90vw; }
.edit-header { 
  display: flex; align-items: baseline; gap: 10px; 
  padding-bottom: 20px; margin-bottom: 4px;
}
.edit-heading { margin: 0; font-size: 17px; color: #0f172a; font-weight: 600; }
.edit-tkt { 
  font-family: 'Times New Roman', Times, serif;
  font-size: 13px; color: #94a3b8; font-weight: 500; letter-spacing: 0.3px;
}

/* 网格布局 */
.edit-grid { 
  display: grid; grid-template-columns: 1fr 1fr; gap: 20px 24px; 
  margin-bottom: 8px;
}
.eg-item { }
.eg-full { grid-column: 1 / -1; }
.eg-label { 
  display: block; font-size: 12px; color: #94a3b8; 
  margin-bottom: 6px; font-weight: 500; letter-spacing: 0.2px;
}
.eg-val { font-size: 14px; color: #0f172a; line-height: 1.5; font-weight: 500; }
.eg-title-text { 
  display: block; padding: 10px 14px; background: #f8fafc;
  border: 1px solid #eef2f6; border-radius: 8px;
  font-size: 14px; color: #334155; line-height: 1.4;
}

/* 自定义下拉框 */
.eg-select-wrap { position: relative; }
.eg-select {
  width: 100%; padding: 10px 36px 10px 14px;
  border: 1px solid #e2e8f0; border-radius: 8px;
  font-size: 14px; color: #0f172a; background: #fff; outline: none;
  -webkit-appearance: none; -moz-appearance: none; appearance: none;
  cursor: pointer; transition: border-color 0.2s;
  font-family: inherit;
}
.eg-select:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
.eg-select-arrow {
  position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
  color: #94a3b8; pointer-events: none;
}

/* 按钮组 */
.edit-actions { 
  display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; 
}
.eg-btn {
  height: 38px; padding: 0 22px; border-radius: 8px;
  font-size: 14px; font-weight: 500; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  transition: all 0.2s; font-family: inherit;
}
.eg-btn-primary { 
  background: #3b82f6; color: #fff; border: none; 
}
.eg-btn-primary:hover { background: #2563eb; }
.eg-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.eg-btn-secondary { 
  background: #fff; color: #475569; border: 1px solid #e2e8f0; 
}
.eg-btn-secondary:hover { border-color: #94a3b8; background: #f8fafc; }

.btn-primary { 
  padding: 12px 24px; 
  border-radius: 8px; 
  border: none; 
  color: #fff; 
  background: #3b82f6; 
  cursor: pointer; 
  font-size: 15px; 
  font-weight: 500;
  flex: 1;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

/* 响应式 */
@media (max-width: 768px) {
  .control-bar { flex-direction: column; gap: 12px; align-items: stretch; }
  .filters { flex-wrap: wrap; }
  .search-input { width: 100%; }
  .drawer-panel { width: 100%; }
}

/* ====== 模态框（新建/编辑） ====== */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.5); z-index: 2000;
  display: flex; align-items: center; justify-content: center; backdrop-filter: blur(3px);
}
.modal-box {
  background: #fff; width: 480px; max-width: 90vw; border-radius: 14px;
  padding: 28px 32px; box-shadow: 0 12px 40px rgba(0,0,0,0.15);
  animation: modalIn .25s ease;
}
@keyframes modalIn { from { opacity: 0; transform: translateY(-20px) scale(.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.modal-box h3 { margin: 0 0 20px; font-size: 18px; color: #0f172a; }
.edit-id { color: #3b82f6; font-size: 14px; font-family: monospace; margin-left: 8px; }
.assign-tkt-id { 
  font-family: 'Times New Roman', Times, serif;
  font-size: 15px; color: #0f172a; font-weight: 700; letter-spacing: 0.5px; margin-left: 6px;
}
.edit-title-preview { font-size: 13px; color: #64748b; margin: -12px 0 18px; padding: 8px 12px; background: #f8fafc; border-radius: 6px; }

.form-field { margin-bottom: 16px; }
.form-field label { display: block; font-size: 13px; color: #475569; margin-bottom: 6px; font-weight: 500; }
.form-field .required { color: #ef4444; }
.form-row { display: flex; gap: 14px; }
.form-row .form-field { flex: 1; }
.text-input { width: 100%; padding: 9px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 14px; outline: none; box-sizing: border-box; transition: border-color .2s; }
.text-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,.1); }
.text-area { resize: vertical; min-height: 80px; font-family: inherit; }
.form-error { margin: 0 0 12px; color: #ef4444; font-size: 13px; background: #fef2f2; padding: 8px 12px; border-radius: 6px; }

.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.btn-cancel { padding: 9px 20px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; color: #475569; cursor: pointer; font-size: 14px; transition: all .2s; }
.btn-cancel:hover { border-color: #94a3b8; }
.btn-primary { padding: 9px 20px; border: none; border-radius: 8px; background: #3b82f6; color: #fff; cursor: pointer; font-size: 14px; font-weight: 500; transition: all .2s; }
.btn-primary:hover { background: #2563eb; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }

/* ====== 4. 布局修复 ====== */
.tickets-page { padding-top: 0; }

/* ====== 删除按钮（红色） ====== */
.btn-outline-danger {
  color: #ef4444 !important;
  border-color: #fca5a5 !important;
}
.btn-outline-danger:hover:not(:disabled) {
  background: #fef2f2 !important;
  border-color: #ef4444 !important;
}
.btn-danger {
  padding: 9px 20px; border: none; border-radius: 8px; background: #ef4444; color: #fff;
  cursor: pointer; font-size: 14px; font-weight: 500; transition: all .2s;
}
.btn-danger:hover { background: #dc2626; }
.btn-danger:disabled { opacity: .5; cursor: not-allowed; }

/* ====== 删除确认弹窗 ====== */
.modal-box-sm { width: 400px; }
.delete-confirm-text {
  font-size: 15px; color: #475569; line-height: 1.6; margin: 0 0 20px;
  text-align: center; padding: 8px 0;
}
.delete-confirm-text strong { color: #0f172a; font-weight: 600; }
.modal-box-sm .modal-actions { justify-content: center; gap: 12px; }

/* ====== 指派模态框 ====== */
.assign-current-info {
  font-size: 14px; color: #475569; margin: -12px 0 16px; padding: 8px 12px;
  background: #f8fafc; border-radius: 6px;
}
.candidate-list { max-height: 300px; overflow-y: auto; margin-bottom: 12px; }
.candidate-item {
  padding: 12px 14px; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 8px;
  cursor: pointer; transition: all 0.2s;
}
.candidate-item:hover { border-color: #93c5fd; background: #f8fafc; }
.candidate-item.selected { border-color: #3b82f6; background: #eff6ff; box-shadow: 0 0 0 2px rgba(59,130,246,0.15); }
.candidate-item.recommended { border-color: #f59e0b; background: #fffbeb; }
.candidate-item.recommended.selected { border-color: #d97706; box-shadow: 0 0 0 2px rgba(245,158,11,0.2); }
.candidate-info { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.candidate-name { font-weight: 600; color: #0f172a; font-size: 15px; }
.candidate-role { color: #64748b; font-size: 13px; }
.candidate-stats { display: flex; gap: 14px; font-size: 13px; color: #64748b; }
.warning-badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
  background: #fef2f2; color: #ef4444; border: 1px solid #fecaca;
}
.recommended-badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
  background: #fffbeb; color: #d97706; border: 1px solid #fde68a;
}

/* ====== Toast 提示条 ====== */
.toast {
  position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
  background: #1e293b; color: #fff; padding: 10px 24px; border-radius: 8px;
  font-size: 14px; z-index: 9999; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  animation: toastIn 0.25s ease;
}
@keyframes toastIn {
  from { opacity: 0; transform: translateX(-50%) translateY(12px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}
</style>