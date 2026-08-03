<script setup lang="ts">
/**
 * StaffListPage.vue — 人员档案查询（重构版）
 * 统计卡片 + 搜索栏 + 表格 + 抽屉详情 + 模态框
 */
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { pushLog } from '../stores/activityLog'

const API = 'http://127.0.0.1:5000'

// ========== 数据 ==========
interface Staff {
  id: number; staff_no: string; name: string; role_name: string
  phone: string; pending_tickets: number; status: string
}
const staffList = ref<Staff[]>([])
const loading = ref(false)
const keyword = ref('')

// ========== 分页 ==========
const currentPage = ref(1)
const pageSize = ref(10)
const totalPages = computed(() => Math.max(1, Math.ceil(staffList.value.length / pageSize.value)))
const paginatedList = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return staffList.value.slice(start, start + pageSize.value)
})
// 页码输入跳转
const pageInput = ref('')
function goToPage() {
  const p = parseInt(pageInput.value)
  if (!isNaN(p) && p >= 1 && p <= totalPages.value) {
    currentPage.value = p
  }
  pageInput.value = ''
}

// 统计信息
const stats = computed(() => ({
  total: staffList.value.length,
  active: staffList.value.filter(s => s.status === '启用').length,
  highLoad: staffList.value.filter(s => s.pending_tickets > 3).length,
}))

// ========== 抽屉详情 ==========
const drawerVisible = ref(false)
const drawerDetail = ref<any>(null)
const drawerLoading = ref(false)

// ========== 新增/编辑模态框 ==========
const modalVisible = ref(false)
const modalTitle = ref('新增运维人员')
const modalForm = ref({ id: 0, name: '', phone: '', role_name: '运维工程师' })
const modalSaving = ref(false)
const roleOptions = ref<string[]>([])

// ========== 加载 ==========
async function loadList() {
  loading.value = true
  try {
    const kw = keyword.value.trim() || undefined
    const res = await axios.get(`${API}/api/staff/list`, { params: kw ? { keyword: kw } : {} })
    staffList.value = res.data || []
    currentPage.value = 1
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadRoles() {
  try {
    const res = await axios.get(`${API}/api/staff/roles`)
    roleOptions.value = (res.data || []).map((r: any) => r.role_name)
    if (!roleOptions.value.includes('运维工程师') && roleOptions.value.length) {
      modalForm.value.role_name = roleOptions.value[0]
    }
  } catch { /* ignore */ }
}

// ========== 搜索 ==========
let searchTimer: number | null = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = window.setTimeout(loadList, 300)
}

// ========== 新增 ==========
function openCreate() {
  modalTitle.value = '新增运维人员'
  modalForm.value = { id: 0, name: '', phone: '', role_name: roleOptions.value[0] || '运维工程师' }
  modalVisible.value = true
}

// ========== 编辑 ==========
function openEdit(row: Staff) {
  modalTitle.value = `编辑人员 - ${row.name}`
  modalForm.value = { id: row.id, name: row.name, phone: row.phone, role_name: row.role_name }
  modalVisible.value = true
}

async function saveModal() {
  modalSaving.value = true
  try {
    if (modalForm.value.id) {
      await axios.put(`${API}/api/staff/${modalForm.value.id}`, {
        name: modalForm.value.name,
        phone: modalForm.value.phone,
        role_name: modalForm.value.role_name,
      })
    } else {
      const res = await axios.post(`${API}/api/staff`, {
        name: modalForm.value.name,
        phone: modalForm.value.phone,
        role_name: modalForm.value.role_name,
      })
      if (!res.data.ok) { alert(res.data.reason); return }
    }
    modalVisible.value = false
    pushLog('当前用户', `${modalTitle.value === '新增运维人员' ? '新增了' : '编辑了'}人员「${modalForm.value.name}」`, modalTitle.value === '新增运维人员' ? 'success' : 'info')
    loadList()
  } catch (e: any) {
    alert(e?.response?.data?.reason || '操作失败')
  } finally {
    modalSaving.value = false
  }
}

// ========== 重置密码 ==========
const resetPwdVisible = ref(false)
const resetPwdRow = ref<{ id: number; name: string; code: string } | null>(null)
const newPassword = ref('123456')
const resetPwdSaving = ref(false)
const resetPwdError = ref('')
const showNewPwd = ref(false)

function openResetPwd(row: any) {
  resetPwdRow.value = { id: row.id, name: row.name, code: row.code }
  newPassword.value = '123456'
  resetPwdError.value = ''
  showNewPwd.value = false
  resetPwdVisible.value = true
}

function randomPassword() {
  // 8位：大小写字母+数字
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789'
  let pwd = ''
  for (let i = 0; i < 8; i++) {
    pwd += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  newPassword.value = pwd
}

async function confirmResetPwd() {
  if (!resetPwdRow.value) return
  const pwd = newPassword.value.trim()
  if (!pwd) { resetPwdError.value = '请输入新密码'; return }
  if (pwd.length < 6) { resetPwdError.value = '密码长度不能少于6位'; return }
  if (pwd.length > 32) { resetPwdError.value = '密码长度不能超过32位'; return }
  resetPwdSaving.value = true
  resetPwdError.value = ''
  try {
    await axios.post(`${API}/api/staff/${resetPwdRow.value.id}/reset-password`, { password: pwd })
    pushLog('当前用户', `重置了「${resetPwdRow.value.name}」的密码`, 'warning')
    resetPwdVisible.value = false
  } catch (e: any) {
    resetPwdError.value = e?.response?.data?.reason || '重置失败'
  } finally {
    resetPwdSaving.value = false
  }
}

// ========== 停用/启用确认 ==========
const statusConfirmVisible = ref(false)
const statusConfirmAction = ref('')
const statusConfirmRow = ref<Staff | null>(null)
const statusConfirmLoading = ref(false)
const statusConfirmError = ref('')

function openStatusConfirm(row: Staff) {
  statusConfirmRow.value = row
  statusConfirmAction.value = row.status === '启用' ? '停用' : '启用'
  statusConfirmError.value = ''
  statusConfirmVisible.value = true
}

async function confirmToggleStatus() {
  if (!statusConfirmRow.value) return
  statusConfirmLoading.value = true
  statusConfirmError.value = ''
  try {
    const res = await axios.put(`${API}/api/staff/${statusConfirmRow.value.id}`, { status: statusConfirmAction.value })
    if (!res.data.ok) {
      statusConfirmError.value = res.data.reason || '操作失败'
      return
    }
    pushLog('当前用户', `${statusConfirmAction.value}了人员「${statusConfirmRow.value.name}」`, 'warning')
    statusConfirmVisible.value = false
    loadList()
  } catch (e: any) {
    if (e?.response?.status === 400) {
      statusConfirmError.value = e.response.data?.reason || '操作失败'
    } else {
      statusConfirmError.value = '网络错误，请重试'
    }
  } finally {
    statusConfirmLoading.value = false
  }
}

// ========== 打开抽屉 ==========
async function openDrawer(row: Staff) {
  drawerVisible.value = true
  drawerLoading.value = true
  try {
    const res = await axios.get(`${API}/api/staff/${row.id}/detail`)
    drawerDetail.value = res.data
  } catch { drawerDetail.value = null } finally { drawerLoading.value = false }
}

// ========== 工单状态颜色（与 TicketsPage 一致） ==========
function getStatusColor(s: string) {
  return ({ '已完成': '#10b981', '进行中': '#3b82f6', '未完成': '#f59e0b' }[s] || '#94a3b8')
}
function getStatusBg(s: string) {
  return ({ '已完成': '#ecfdf5', '进行中': '#eff6ff', '未完成': '#fef3c7' }[s] || '#f1f5f9')
}

// ========== 手机号打码 ==========
function maskPhone(phone: string) {
  if (!phone || phone.length < 7) return phone
  return phone.slice(0, 3) + '****' + phone.slice(-4)
}

// ========== 头像颜色 ==========
const colorPalette = ['#1890ff', '#52c41a', '#fa8c16', '#eb2f96', '#722ed1', '#13c2c2', '#fa541c']
function avatarColor(name: string) {
  let hash = 0
  for (const ch of name) hash = ch.charCodeAt(0) + ((hash << 5) - hash)
  return colorPalette[Math.abs(hash) % colorPalette.length]
}

onMounted(() => { loadRoles(); loadList() })
</script>

<template>
  <div class="staff-list-page">
    <!-- 标题 -->
    <div class="title-row">
      <h2 class="page-title">人员档案查询</h2>
      <button class="refresh-btn" @click="loadList">⟳ 刷新</button>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card" style="--c:#1890ff">
        <div class="stat-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg></div>
        <div class="stat-info"><span class="stat-num">{{ stats.total }}</span><span class="stat-lbl">总人数</span></div>
      </div>
      <div class="stat-card" style="--c:#52c41a">
        <div class="stat-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"/></svg></div>
        <div class="stat-info"><span class="stat-num">{{ stats.active }}</span><span class="stat-lbl">在职人数</span></div>
      </div>
      <div class="stat-card" style="--c:#fa8c16">
        <div class="stat-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></div>
        <div class="stat-info"><span class="stat-num">{{ stats.highLoad }}</span><span class="stat-lbl">高负荷人员</span></div>
      </div>
    </div>

    <!-- 控制栏 -->
    <div class="control-bar">
      <div class="search-box">
        <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
        </svg>
        <input v-model="keyword" @input="onSearchInput" placeholder="搜索姓名、手机号或工号..." class="search-input" />
      </div>
      <div class="ctrl-actions">
        <button class="ctrl-btn" @click="openCreate">+ 新增人员</button>
      </div>
    </div>

    <!-- 表格 -->
    <div class="table-card">
      <div class="table-scroll">
      <table class="data-table" v-if="!loading">
        <thead>
          <tr>
            <th>工号</th>
            <th>姓名</th>
            <th>岗位角色</th>
            <th>标签</th>
            <th>手机号</th>
            <th>待处理</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in paginatedList" :key="row.id" class="clickable-row">
            <td class="td-no">{{ row.staff_no }}</td>
            <td>
              <span class="avatar-dot" :style="{ background: avatarColor(row.name) }">{{ row.name[0] }}</span>
              <span class="staff-name">{{ row.name }}</span>
            </td>
            <td><span class="role-tag">{{ row.role_name }}</span></td>
            <td class="td-tags">
              <span v-for="t in row.tags || []" :key="t.tag_id" class="staff-tag" :style="{ color: t.tag_color, borderColor: t.tag_color, background: t.tag_color + '14' }">
                {{ t.tag_name }}
              </span>
              <span v-if="!(row.tags || []).length" class="td-muted">-</span>
            </td>
            <td class="td-muted">{{ maskPhone(row.phone) }}</td>
            <td>
              <span class="pending-badge" :class="{ high: row.pending_tickets > 3, zero: row.pending_tickets === 0 }">
                {{ row.pending_tickets }}
              </span>
            </td>
            <td>
              <span class="status-tag" :class="row.status">{{ row.status }}</span>
            </td>
            <td class="td-actions" @click.stop>
              <button class="act-btn" @click="openDrawer(row)" title="查看详情">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
              <button class="act-btn" @click="openEdit(row)" title="编辑">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="act-btn" @click="openResetPwd(row)" title="重置密码">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              </button>
              <button class="act-btn" :class="{ danger: row.status === '启用' }"
                @click="openStatusConfirm(row)" :title="row.status === '启用' ? '停用' : '启用'">
                <svg v-if="row.status === '启用'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><line x1="3" y1="11" x2="3" y2="7a9 9 0 0 1 18 0v4"/></svg>
                <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </td>
          </tr>
          <tr v-if="staffList.length === 0">
            <td colspan="8" class="empty-row">暂无数据</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="loading-text">加载中...</div>
      </div>

      <!-- 分页 -->
      <div class="pagination-bar" v-if="!loading && staffList.length > 0">
        <span class="pg-info">共 {{ staffList.length }} 条 · 每页 {{ pageSize }} 条</span>
        <div class="pg-controls">
          <button class="pg-btn" :disabled="currentPage === 1" @click="currentPage = 1">«</button>
          <button class="pg-btn" :disabled="currentPage === 1" @click="currentPage--">‹</button>
          <span class="pg-current">{{ currentPage }} / {{ totalPages }}</span>
          <button class="pg-btn" :disabled="currentPage === totalPages" @click="currentPage++">›</button>
          <button class="pg-btn" :disabled="currentPage === totalPages" @click="currentPage = totalPages">»</button>
          <div class="pg-jump">
            跳转
            <input v-model="pageInput" @keyup.enter="goToPage" type="number" min="1" :max="totalPages" class="pg-input" />
            页
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧抽屉（人员档案详情） -->
    <div class="drawer-overlay" v-if="drawerVisible" @click.self="drawerVisible = false">
      <div class="drawer-panel">
        <div class="drawer-header">
          <div class="drawer-title-wrap">
            <div class="d-avatar" :style="{ background: drawerDetail ? '#eef2ff' : '#e2e8f0' }">
              <span class="d-avatar-text" :style="{ color: drawerDetail ? '#4f46e5' : '#94a3b8' }">{{ drawerDetail?.name?.[0] || '?' }}</span>
            </div>
            <div>
              <h3 class="drawer-title">{{ drawerDetail?.name || '人员详情' }}</h3>
              <span class="drawer-subtitle">{{ drawerDetail?.role_name || '' }}</span>
            </div>
          </div>
          <button class="drawer-close" @click="drawerVisible = false">✕</button>
        </div>

        <div class="drawer-body" v-if="!drawerLoading && drawerDetail">
          <!-- 人员信息卡片 -->
          <div class="staff-info-card">
            <div class="si-table">
              <div class="si-cell">
                <svg class="si-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#64748b" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="12" y2="17"/></svg>
                <span class="si-label">工号</span>
                <span class="si-value">{{ drawerDetail.staff_no }}</span>
              </div>
              <div class="si-cell">
                <svg class="si-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#64748b" stroke-width="1.5"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                <span class="si-label">手机号</span>
                <span class="si-value">{{ maskPhone(drawerDetail.phone) }}</span>
              </div>
              <div class="si-cell">
                <svg class="si-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#64748b" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span class="si-label">状态</span>
                <span class="si-value si-status" :class="drawerDetail.status">{{ drawerDetail.status }}</span>
              </div>
              <div class="si-cell">
                <svg class="si-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#64748b" stroke-width="1.5"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                <span class="si-label">入职时间</span>
                <span class="si-value">{{ drawerDetail.created_at?.slice(0, 10) || '-' }}</span>
              </div>
              <div class="si-cell">
                <svg class="si-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#64748b" stroke-width="1.5"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
                <span class="si-label">标签</span>
                <span class="si-value">
                  <span v-for="t in drawerDetail.tags || []" :key="t.tag_id" class="staff-tag" :style="{ color: t.tag_color, borderColor: t.tag_color, background: t.tag_color + '14' }">
                    {{ t.tag_name }}
                  </span>
                  <span v-if="!(drawerDetail.tags || []).length">-</span>
                </span>
              </div>
            </div>
          </div>

          <!-- 待处理工单 -->
          <div class="ticket-section">
            <h4 class="ts-title">待处理工单 <span class="ts-count">{{ drawerDetail.recent_tickets?.length || 0 }}</span></h4>
            <div v-if="drawerDetail.recent_tickets?.length" class="ts-list">
              <div v-for="t in drawerDetail.recent_tickets" :key="t.id" class="ts-item">
                <div class="ts-left">
                  <span class="ts-id">{{ t.id }}</span>
                  <span class="ts-desc">{{ t.title }}</span>
                </div>
                <div class="ts-right">
                  <span class="ts-status" :style="{ background: getStatusBg(t.status), color: getStatusColor(t.status) }">
                    {{ t.status }}
                  </span>
                  <svg class="ts-arrow" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#cbd5e1" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </div>
              </div>
            </div>
            <p v-else class="ts-empty">暂无待处理工单</p>
          </div>
        </div>
        <div v-else class="drawer-loading">加载中...</div>
      </div>
    </div>

    <!-- 新增/编辑模态框 -->
    <div class="modal-overlay" v-if="modalVisible" @click.self="modalVisible = false">
      <div class="modal-box">
        <h3 class="modal-title">{{ modalTitle }}</h3>
        <div class="modal-fields">
          <div class="field-row">
            <label>姓名</label>
            <input v-model="modalForm.name" placeholder="请输入姓名" class="field-input" />
          </div>
          <div class="field-row">
            <label>手机号</label>
            <input v-model="modalForm.phone" placeholder="请输入手机号" class="field-input" />
          </div>
          <div class="field-row">
            <label>岗位角色</label>
            <select v-model="modalForm.role_name" class="field-input">
              <option v-for="r in roleOptions" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
        </div>
        <div class="modal-actions">
          <button class="mbtn mbtn-cancel" @click="modalVisible = false">取消</button>
          <button class="mbtn mbtn-primary" @click="saveModal" :disabled="modalSaving">{{ modalSaving ? '保存中...' : '确定' }}</button>
        </div>
      </div>
    </div>

    <!-- 重置密码模态框 -->
    <div class="modal-overlay" v-if="resetPwdVisible" @click.self="resetPwdVisible = false">
      <div class="modal-box reset-pwd-box">
        <div class="reset-pwd-header">
          <div class="reset-pwd-icon">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </div>
          <div>
            <h3 class="modal-title" style="margin: 0;">重置密码</h3>
            <p class="reset-pwd-sub">为「{{ resetPwdRow?.name }}」({{ resetPwdRow?.code }}) 设置新密码</p>
          </div>
        </div>

        <div class="reset-pwd-fields">
          <label class="reset-pwd-label">新密码</label>
          <div class="reset-pwd-input-wrap">
            <input
              :type="showNewPwd ? 'text' : 'password'"
              v-model="newPassword"
              class="reset-pwd-input"
              placeholder="请输入新密码（6-32位）"
              maxlength="32"
              @keyup.enter="confirmResetPwd" />
            <button type="button" class="reset-pwd-eye" @click="showNewPwd = !showNewPwd" :title="showNewPwd ? '隐藏密码' : '显示密码'">
              <svg v-if="!showNewPwd" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            </button>
          </div>
          <div class="reset-pwd-tip">
            <span>默认密码：123456</span>
            <button type="button" class="reset-pwd-random" @click="randomPassword">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
              随机生成
            </button>
          </div>
          <p v-if="resetPwdError" class="reset-pwd-error">{{ resetPwdError }}</p>
        </div>

        <div class="modal-actions">
          <button class="mbtn mbtn-cancel" @click="resetPwdVisible = false" :disabled="resetPwdSaving">取消</button>
          <button class="mbtn mbtn-primary" @click="confirmResetPwd" :disabled="resetPwdSaving">
            {{ resetPwdSaving ? '重置中...' : '确认重置' }}
          </button>
        </div>
      </div>
    </div>
    <!-- 停用/启用确认模态框 -->
    <div class="modal-overlay" v-if="statusConfirmVisible" @click.self="statusConfirmVisible = false">
      <div class="modal-box confirm-box">
        <div class="confirm-icon">⚠️</div>
        <h3 class="confirm-title">确认{{ statusConfirmAction }}</h3>
        <p class="confirm-text">确定{{ statusConfirmAction }}「{{ statusConfirmRow?.name }}」吗？</p>
        <p v-if="statusConfirmError" class="confirm-error">{{ statusConfirmError }}</p>
        <div class="modal-actions">
          <button class="mbtn mbtn-cancel" @click="statusConfirmVisible = false" :disabled="statusConfirmLoading">取消</button>
          <button class="mbtn mbtn-danger" @click="confirmToggleStatus" :disabled="statusConfirmLoading">
            {{ statusConfirmLoading ? '处理中...' : '确认' + statusConfirmAction }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.staff-list-page {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: calc((100vh - 60px) / 0.85);
  box-sizing: border-box;
  padding: 4px 4px 0;
}

/* 标题 */
.title-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-title { margin: 0; font-size: 22px; font-weight: 700; color: #0f172a; }
.refresh-btn {
  padding: 6px 18px; border: 1px solid #e2e8f0; border-radius: 8px;
  background: #fff; color: #64748b; font-size: 13px; cursor: pointer; transition: all 0.2s;
}
.refresh-btn:hover { border-color: #1890ff; color: #1890ff; background: #f0f7ff; }

/* 统计卡片 */
.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 12px; flex-shrink: 0; }
.stat-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05); display: flex; align-items: center; gap: 14px;
  border: 1px solid #eef2f6;
}
.stat-icon {
  color: var(--c, #64748b); flex-shrink: 0;
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--c, #64748b) 12%, transparent);
}
.stat-info { display: flex; flex-direction: column; }
.stat-num { font-size: 24px; font-weight: 700; color: #0f172a; line-height: 1.2; }
.stat-lbl { font-size: 12px; color: #94a3b8; margin-top: 1px; }

/* 控制栏 */
.control-bar {
  display: flex; align-items: center; gap: 12px; justify-content: space-between;
  background: #fff; border-radius: 10px; padding: 12px 16px;
  margin-bottom: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  flex-shrink: 0;
}
.ctrl-actions { display: flex; gap: 10px; flex-shrink: 0; }
.ctrl-btn { 
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
.ctrl-btn:hover { background: #f8fafc; border-color: #94a3b8; }
.search-box {
  flex: 1; display: flex; align-items: center; gap: 8px;
  background: #f8fafc; border-radius: 8px; padding: 8px 14px;
  border: 1px solid #e2e8f0; transition: border-color 0.2s;
}
.search-box:focus-within { border-color: #1890ff; }
.search-icon { color: #94a3b8; flex-shrink: 0; }
.search-input { flex: 1; border: none; background: none; outline: none; font-size: 14px; color: #1e293b; }
.search-input::placeholder { color: #94a3b8; }

/* 表格卡片 */
.table-card {
  background: #fff; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); overflow: hidden;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.table-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th {
  background: #f8fafc; padding: 14px 16px; text-align: center;
  font-weight: 600; color: #475569; border-bottom: 1px solid #e2e8f0;
  font-size: 13px; vertical-align: middle; white-space: nowrap;
}
.data-table td { padding: 14px 16px; border-bottom: 1px solid #f1f5f9; color: #334155; vertical-align: middle; font-size: 14px; text-align: center; }
.data-table td > * { vertical-align: middle; }
.clickable-row { cursor: pointer; transition: background 0.15s; }
.clickable-row:hover { background: #f8fafc; }
.td-no { font-family: 'Times New Roman', Times, serif; font-weight: 500; color: #0f172a; font-size: 14px; }
.td-muted { color: #94a3b8; }
.td-tags { min-width: 140px; white-space: nowrap; }

/* 头像 */
.avatar-dot {
  display: none; /* 去掉彩色头像，只显示姓名 */
}
.staff-name { font-weight: 500; color: #0f172a; font-size: 14px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; }
.role-tag {
  display: inline-block; padding: 2px 10px; border-radius: 4px;
  background: #f1f5f9; color: #475569; font-size: 12px; font-weight: 500;
  white-space: nowrap;
}
.staff-tag {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  font-size: 11px; font-weight: 500; border: 1px solid; margin: 1px 3px 1px 0;
  white-space: nowrap; line-height: 1.4;
}
.pending-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 28px; height: 28px; border-radius: 50%;
  background: #f1f5f9; color: #475569; font-weight: 600; font-size: 13px;
}
.pending-badge.high { background: #fef2f2; color: #dc2626; }
.pending-badge.zero { background: #f8fafc; color: #94a3b8; }
.status-tag { padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.status-tag.启用 { background: #f0fdf4; color: #16a34a; }
.status-tag.停用 { background: #fef2f2; color: #dc2626; }

/* 操作按钮（灰色图标） */
.td-actions { white-space: nowrap; display: flex; gap: 4px; align-items: center; justify-content: center; }
.act-btn {
  width: 30px; height: 30px; padding: 0; border: 1px solid #e2e8f0; border-radius: 6px;
  background: #fff; cursor: pointer; color: #94a3b8;
  display: inline-flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.act-btn:hover { border-color: #cbd5e1; color: #475569; background: #f8fafc; }
.empty-row { text-align: center; color: #94a3b8; padding: 40px !important; }
.loading-text { padding: 40px; text-align: center; color: #94a3b8; }

/* 分页 */
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 4px;
  font-size: 13px;
  color: #64748b;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  flex-shrink: 0;
  background: #fff;
  border-top: 1px solid #f1f5f9;
}
.pg-info { color: #94a3b8; }
.pg-controls { display: flex; align-items: center; gap: 6px; }
.pg-btn {
  min-width: 28px;
  height: 28px;
  padding: 0 8px;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #475569;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: all 0.15s;
}
.pg-btn:hover:not(:disabled) { border-color: #3b82f6; color: #3b82f6; }
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pg-current {
  display: inline-block;
  min-width: 56px;
  text-align: center;
  font-weight: normal;
  color: #0f172a;
  font-size: 13px;
}
.pg-jump {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 10px;
  color: #64748b;
  font-size: 13px;
}
.pg-input {
  width: 50px;
  height: 28px;
  padding: 0 6px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
  text-align: center;
  font-family: inherit;
  color: #0f172a;
  outline: none;
  transition: border-color 0.15s;
}
.pg-input:focus { border-color: #3b82f6; }
.pg-input::-webkit-outer-spin-button,
.pg-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }

/* 抽屉（人员档案详情） */
.drawer-overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.4); z-index: 1000; display: flex; justify-content: flex-end; }
.drawer-panel { width: 440px; background: #fff; height: 100%; overflow-y: auto; box-shadow: -4px 0 24px rgba(0,0,0,0.1); animation: slideIn 0.25s ease; padding-top: 60px; box-sizing: border-box; }
@keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
.drawer-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px; border-bottom: 1px solid #eef2f6; }
.drawer-title-wrap { display: flex; align-items: center; gap: 14px; }
.d-avatar {
  width: 44px; height: 44px; border-radius: 12px; display: flex;
  align-items: center; justify-content: center; flex-shrink: 0;
}
.d-avatar-text { font-size: 18px; font-weight: 600; }
.drawer-title { margin: 0; font-size: 16px; font-weight: 600; color: #0f172a; }
.drawer-subtitle { font-size: 13px; color: #64748b; margin-top: 2px; display: block; }
.drawer-close {
  width: 30px; height: 30px; display: flex; align-items: center; justify-content: center;
  border: none; background: #f1f5f9; border-radius: 6px;
  font-size: 14px; cursor: pointer; color: #94a3b8; transition: all 0.15s;
  padding: 0; line-height: 1;
}
.drawer-close:hover { background: #e2e8f0; color: #475569; }
.drawer-body { padding: 24px; }

/* 人员信息卡片（网格布局） */
.staff-info-card {
  background: #f8f9fb; padding: 20px; border-radius: 12px;
  margin-bottom: 24px; border: 1px solid #eef0f4;
}
.si-table { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 20px; align-items: start; }
.si-cell { display: flex; flex-direction: column; gap: 3px; align-items: flex-start; }
.si-icon { margin-bottom: 2px; }
.si-label { font-size: 11px; color: #94a3b8; font-weight: 500; letter-spacing: 0.3px; }
.si-value { font-size: 14px; color: #1e293b; font-weight: 600; line-height: 1.2; }

/* 状态标签 — 与 si-value 同结构，底色+彩色 */
.si-status {
  padding: 2px 10px 2px 0; border-radius: 6px; font-size: 13px;
  background: transparent; color: #16a34a; width: fit-content;
  display: inline-flex; align-items: center; gap: 6px;
}
.si-status::before {
  content: ''; width: 8px; height: 8px; border-radius: 50%;
  background: currentColor; opacity: 0.85;
}
.si-status.启用 { color: #16a34a; }
.si-status.停用 { color: #dc2626; }

/* 待处理工单 */
.ticket-section { }
.ts-title {
  font-size: 14px; font-weight: 600; color: #0f172a;
  margin: 0 0 14px; display: flex; align-items: center; gap: 8px;
}
.ts-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 22px; height: 22px; background: #f1f5f9; color: #64748b;
  border-radius: 11px; font-size: 12px; font-weight: 500; padding: 0 6px;
}
.ts-list { display: flex; flex-direction: column; gap: 8px; }
.ts-item {
  padding: 14px 16px; background: #f8fafc; border: 1px solid #eef2f6;
  border-radius: 10px; display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; transition: all 0.15s;
}
.ts-item:hover { background: #fff; border-color: #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.ts-item:hover .ts-arrow { stroke: #64748b; }
.ts-left { display: flex; align-items: center; gap: 10px; overflow: hidden; flex: 1; }
.ts-id {
  font-family: 'Times New Roman', Times, serif; font-size: 13px;
  color: #0f172a; font-weight: 500; white-space: nowrap;
  flex-shrink: 0;
}
.ts-desc { font-size: 13px; color: #334155; font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ts-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ts-status {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 600;
}
.ts-status svg { flex-shrink: 0; }
.ts-arrow { transition: stroke 0.15s; }
.ts-empty { color: #94a3b8; font-size: 13px; padding: 16px 0; }
.drawer-loading { padding: 40px; text-align: center; color: #94a3b8; }

/* 模态框 */
.modal-overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.5); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.modal-box { background: #fff; width: 440px; border-radius: 16px; padding: 28px 32px; box-shadow: 0 8px 30px rgba(0,0,0,0.15); }
.modal-title { margin: 0 0 20px; font-size: 17px; font-weight: 700; color: #0f172a; }
.modal-fields { display: flex; flex-direction: column; gap: 14px; margin-bottom: 20px; }
.field-row { display: flex; flex-direction: column; gap: 4px; }
.field-row label { font-size: 12px; color: #64748b; font-weight: 500; }
.field-input {
  padding: 9px 12px; border: 1px solid #e2e8f0; border-radius: 8px;
  font-size: 14px; outline: none; transition: border-color 0.2s; background: #f8fafc;
}
.field-input:focus { border-color: #1890ff; background: #fff; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
.mbtn {
  padding: 9px 24px; border-radius: 8px; font-size: 14px; font-weight: 600;
  cursor: pointer; transition: all 0.2s; border: none;
}
.mbtn-cancel { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
.mbtn-cancel:hover { background: #e2e8f0; }
.mbtn-primary { background: #3b82f6; color: #fff; }
.mbtn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.mbtn-primary:hover { background: #2563eb; }
.mbtn-danger { background: #ef4444; color: #fff; }
.mbtn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
.mbtn-danger:hover { background: #dc2626; }

/* 确认弹窗 */
.confirm-box { text-align: center; }
.confirm-icon { font-size: 36px; margin-bottom: 8px; }
.confirm-title { margin: 0 0 8px; font-size: 17px; }
.confirm-text { margin: 0 0 16px; font-size: 14px; color: #64748b; }
.confirm-error { margin: 0 0 12px; color: #dc2626; font-size: 13px; background: #fef2f2; padding: 8px 12px; border-radius: 8px; }
.confirm-box .modal-actions { justify-content: center; }

/* 重置密码模态框 */
.reset-pwd-box { width: 480px; padding: 24px 28px; }
.reset-pwd-header { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; padding-bottom: 18px; border-bottom: 1px solid #f1f5f9; }
.reset-pwd-icon {
  width: 44px; height: 44px;
  border-radius: 10px;
  background: #eff6ff;
  color: #3b82f6;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.reset-pwd-sub { margin: 4px 0 0; font-size: 12px; color: #64748b; font-weight: normal; }
.reset-pwd-fields { margin-bottom: 20px; }
.reset-pwd-label { display: block; font-size: 13px; color: #475569; font-weight: 600; margin-bottom: 8px; }
.reset-pwd-input-wrap { position: relative; display: flex; align-items: center; }
.reset-pwd-input {
  flex: 1;
  width: 100%;
  padding: 10px 40px 10px 12px;
  font-size: 14px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  outline: none;
  color: #0f172a;
  background: #fff;
  transition: all 0.2s;
  letter-spacing: 1px;
}
.reset-pwd-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12); }
.reset-pwd-eye {
  position: absolute;
  right: 8px;
  background: transparent;
  border: 0;
  padding: 4px;
  cursor: pointer;
  color: #94a3b8;
  display: flex; align-items: center; justify-content: center;
  border-radius: 4px;
  transition: color 0.15s;
}
.reset-pwd-eye:hover { color: #3b82f6; }
.reset-pwd-tip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
  color: #94a3b8;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.reset-pwd-random {
  display: inline-flex; align-items: center; gap: 4px;
  background: transparent;
  border: 1px solid #cbd5e1;
  color: #3b82f6;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  transition: all 0.15s;
}
.reset-pwd-random:hover { background: #eff6ff; border-color: #3b82f6; }
.reset-pwd-error {
  margin: 8px 0 0;
  padding: 6px 10px;
  background: #fef2f2;
  color: #dc2626;
  border-radius: 6px;
  font-size: 12px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
</style>
