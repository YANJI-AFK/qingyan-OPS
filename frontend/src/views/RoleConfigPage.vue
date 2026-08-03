<script setup lang="ts">
/**
 * RoleConfigPage.vue — 岗位角色配置（极简双栏不滚动布局版）
 * 角色卡片列表 + 新增/编辑/删除 + 人员统计 + 默认角色
 */
import { ref, onMounted, onBeforeUnmount, nextTick, computed } from 'vue'
import axios from 'axios'

const API = 'http://127.0.0.1:5000'

interface Role {
  role_id: number
  role_name: string
  created_at: string
  staff_count: number
  tag_id: number | null
  tag_name: string | null
  tag_color: string | null
  tags: Tag[]
}
const roles = ref<Role[]>([])
const loading = ref(false)

const newRoleName = ref('')
const adding = ref(false)
const msg = ref('')
const msgErr = ref(false)

// 最近创建的角色（最新的5个）
const recentRoles = computed(() =>
  [...roles.value].sort((a, b) => b.role_id - a.role_id).slice(0, 5)
)

// 删除标签确认弹窗
const deleteTagConfirm = ref<{ tagId: number; tagName: string; tagColor: string } | null>(null)

// 自定义下拉
const dropdownOpen = ref(false)
const dropdownMaxHeight = ref(180)
const selectWrapRef = ref<HTMLElement | null>(null)

function toggleDropdown() {
  if (dropdownOpen.value) { dropdownOpen.value = false; return }
  // 打开前测量可用空间，确保下拉框不超出卡片底部
  if (selectWrapRef.value) {
    const rect = selectWrapRef.value.getBoundingClientRect()
    const cardEl = selectWrapRef.value.closest('.action-card') as HTMLElement | null
    const cardBottom = cardEl ? cardEl.getBoundingClientRect().bottom : window.innerHeight
    const gap = 4  // 弹出框到按钮 + 卡片底部的间隙
    const available = Math.floor(cardBottom - rect.bottom - gap)
    // 至少留 40px（2 项高度），否则启用 0 即不显示滚动超出部分
    dropdownMaxHeight.value = Math.max(0, available)
  }
  dropdownOpen.value = true
}

const defaultRoleName = ref('')

// 编辑
const editing = ref(false)
const editId = ref(0)
const editName = ref('')

// ========== 标签管理 ==========
interface Tag {
  tag_id: number
  tag_name: string
  tag_color: string
}
const tags = ref<Tag[]>([])
const newTagName = ref('')
const newTagColor = ref('#3b82f6')
const addingTag = ref(false)
const tagMsg = ref('')
const tagMsgErr = ref(false)
const filterTagId = ref<number | null>(null)

// 标签预设颜色
const presetColors = ['#3b82f6', '#6366f1', '#0ea5e9', '#14b8a6', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#ec4899', '#f97316']

async function loadTags() {
  try {
    const res = await axios.get(`${API}/api/staff/role-tags`)
    tags.value = res.data || []
  } catch { /* ignore */ }
}

async function addTag() {
  const name = newTagName.value.trim()
  if (!name) { tagMsg.value = '标签名不能为空'; tagMsgErr.value = true; return }
  addingTag.value = true; tagMsg.value = ''; tagMsgErr.value = false
  try {
    const res = await axios.post(`${API}/api/staff/role-tags`, { tag_name: name, tag_color: newTagColor.value })
    if (res.data.ok) {
      newTagName.value = ''
      tagMsg.value = '标签添加成功'; tagMsgErr.value = false
      setTimeout(() => tagMsg.value = '', 2000)
      loadTags()
    } else {
      tagMsg.value = res.data.reason || '新增失败'; tagMsgErr.value = true
    }
  } catch (e: any) {
    tagMsg.value = e?.response?.data?.reason || '新增失败'; tagMsgErr.value = true
  } finally { addingTag.value = false }
}

function askDeleteTag(tagId: number) {
  const t = tags.value.find(t => t.tag_id === tagId)
  if (!t) return
  deleteTagConfirm.value = { tagId, tagName: t.tag_name, tagColor: t.tag_color }
}

function cancelDeleteTag() {
  deleteTagConfirm.value = null
}

async function confirmDeleteTag() {
  if (!deleteTagConfirm.value) return
  const id = deleteTagConfirm.value.tagId
  deleteTagConfirm.value = null
  try {
    const res = await axios.delete(`${API}/api/staff/role-tags?tag_id=${id}`)
    if (res.data.ok) {
      if (filterTagId.value === id) filterTagId.value = null
      loadTags()
      loadRoles()
    }
  } catch { /* ignore */ }
}

async function setRoleTag(roleId: number, tagId: number) {
  try {
    await axios.post(`${API}/api/staff/roles/tag`, { role_id: roleId, tag_id: tagId })
    loadRoles()
  } catch { /* ignore */ }
}

// 按标签筛选角色
const filteredRoles = computed(() => {
  if (filterTagId.value === null) return roles.value
  return roles.value.filter(r => (r.tags || []).some(t => t.tag_id === filterTagId.value))
})

// 风格色系 (调整为更高级、低饱和度的莫兰迪/现代灰彩色系)
const accentColors = ['#3b82f6', '#6366f1', '#0ea5e9', '#14b8a6', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6']
function roleAccent(idx: number) { return accentColors[idx % accentColors.length] }

// 计算总人数用于展示更丰富的数据视角
const totalStaffCount = computed(() => roles.value.reduce((sum, r) => sum + (r.staff_count || 0), 0))

async function loadRoles() {
  loading.value = true
  try {
    const res = await axios.get(`${API}/api/staff/roles`)
    roles.value = res.data || []
  } catch { /* ignore */ } finally { loading.value = false }
}

async function addRole() {
  const name = newRoleName.value.trim()
  if (!name) { msg.value = '角色名不能为空'; msgErr.value = true; return }
  adding.value = true; msg.value = ''; msgErr.value = false
  try {
    const res = await axios.post(`${API}/api/staff/roles`, { role_name: name })
    if (res.data.ok) {
      newRoleName.value = ''
      msg.value = '角色添加成功'; msgErr.value = false
      setTimeout(() => msg.value = '', 2000)
      loadRoles()
    } else {
      msg.value = res.data.reason || '新增失败'; msgErr.value = true
    }
  } catch (e: any) {
    msg.value = e?.response?.data?.reason || '新增失败'; msgErr.value = true
  } finally { adding.value = false }
}

// 编辑
const editTagIds = ref<number[]>([])
function startEdit(r: Role) {
  editing.value = true
  editId.value = r.role_id
  editName.value = r.role_name
  editTagIds.value = (r.tags || []).map(t => t.tag_id)
}
function cancelEdit() {
  editing.value = false; editId.value = 0; editName.value = ''
  editTagIds.value = []
}
async function saveEdit() {
  const name = editName.value.trim()
  if (!name) { msg.value = '角色名不能为空'; msgErr.value = true; return }
  msg.value = ''; msgErr.value = false
  try {
    const res = await axios.put(`${API}/api/staff/roles`, { role_id: editId.value, role_name: name })
    if (res.data.ok) {
      // 保存多标签
      await axios.post(`${API}/api/staff/roles/tags`, { role_id: editId.value, tag_ids: editTagIds.value })
      cancelEdit()
      msg.value = '角色已更新'; msgErr.value = false
      setTimeout(() => msg.value = '', 2000)
      loadRoles()
    } else {
      msg.value = res.data.reason || '编辑失败'; msgErr.value = true
    }
  } catch (e: any) {
    msg.value = e?.response?.data?.reason || '编辑失败'; msgErr.value = true
  }
}

async function deleteRole(roleId: number, roleName: string) {
  if (!confirm(`确定删除角色「${roleName}」吗？操作不可逆。`)) return
  try {
    const res = await axios.delete(`${API}/api/staff/roles?role_id=${roleId}`)
    if (res.data.ok) {
      msg.value = '角色已删除'; msgErr.value = false
      setTimeout(() => msg.value = '', 2000)
      loadRoles()
    } else {
      msg.value = res.data.reason; msgErr.value = true
    }
  } catch (e: any) {
    msg.value = e?.response?.data?.reason || '删除失败'; msgErr.value = true
  }
}

function closeDropdown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.select-wrap')) dropdownOpen.value = false
}

onMounted(() => {
  loadRoles(); loadTags()
  document.addEventListener('click', closeDropdown)
})
onBeforeUnmount(() => { document.removeEventListener('click', closeDropdown) })
</script>

<template>
  <div class="roles-page">
    <!-- 顶部标题区 -->
    <header class="page-header">
      <div class="header-left">
        <h2 class="page-title">岗位角色配置</h2>
      </div>
      <div class="header-stats" v-if="!loading">
        <div class="stat-card" style="--stat-color: #3b82f6">
          <div class="stat-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
          </div>
          <div class="stat-body">
            <span class="stat-val">{{ roles.length }}</span>
            <span class="stat-lbl">有效角色</span>
          </div>
        </div>
        <div class="stat-card" style="--stat-color: #10b981">
          <div class="stat-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div class="stat-body">
            <span class="stat-val">{{ totalStaffCount }}</span>
            <span class="stat-lbl">已分配人员</span>
          </div>
        </div>
      </div>
    </header>

    <!-- 主体双栏布局 -->
    <div class="main-layout">
      
      <!-- 左侧操作栏 -->
      <aside class="side-panel">
        <!-- 新增角色模块 -->
<section class="action-card create-role-card">
  <div class="card-title-row">
    <span class="icon-badge" style="--ico: #3b82f6">
      <svg class="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>
    </span>
    <h3>新建岗位角色</h3>
  </div>
  <div class="form-group">
    <input v-model="newRoleName" placeholder="例如：数据库管理员" class="custom-input" @keyup.enter="addRole" />
    <button class="btn-primary" @click="addRole" :disabled="adding">
      {{ adding ? '提交中...' : '确认新建' }}
    </button>
  </div>
  <Transition name="fade">
    <p v-if="msg" class="status-msg" :class="{ 'is-error': msgErr }">
      {{ msgErr ? '✕' : '✓' }} {{ msg }}
    </p>
  </Transition>
  <div v-if="recentRoles.length" class="recent-role-list">
    <div class="recent-header">
      <span>最近创建</span>
      <span class="recent-count-badge">{{ recentRoles.length }}</span>
    </div>
    <div class="recent-items">
      <div v-for="r in recentRoles" :key="r.role_id" class="recent-item">
        <span class="recent-avatar" :style="{ background: r.tag_color || '#e2e8f0', color: r.tag_color ? '#fff' : '#94a3b8' }">{{ r.role_name.charAt(0) }}</span>
        <span class="recent-name">{{ r.role_name }}</span>
        <span class="recent-count">{{ r.staff_count }}人</span>
      </div>
    </div>
  </div>
</section>

        <!-- 角色分类/标签管理 -->
        <section class="action-card">
          <div class="card-title-row">
            <span class="icon-badge" style="--ico: #f59e0b">
              <svg class="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
            </span>
            <h3>角色分类/标签管理</h3>
          </div>
          <div class="form-group">
            <div class="tag-input-row">
              <input v-model="newTagName" placeholder="输入标签名" class="custom-input" @keyup.enter="addTag" />
              <div class="color-picker-row">
                <button v-for="c in presetColors" :key="c" class="color-dot" :class="{ active: newTagColor === c }" :style="{ backgroundColor: c }" @click="newTagColor = c" />
              </div>
            </div>
            <button class="btn-primary" @click="addTag" :disabled="addingTag">
              {{ addingTag ? '提交中...' : '确认新建' }}
            </button>
          </div>
          <Transition name="fade">
            <p v-if="tagMsg" class="status-msg" :class="{ 'is-error': tagMsgErr }">
              {{ tagMsgErr ? '✕' : '✓' }} {{ tagMsg }}
            </p>
          </Transition>
          <div v-if="tags.length" class="tag-list">
            <span
              v-for="t in tags"
              :key="t.tag_id"
              class="tag-badge"
              :class="{ active: filterTagId === t.tag_id }"
              :style="{ '--tag-color': t.tag_color }"
              @click="filterTagId = filterTagId === t.tag_id ? null : t.tag_id"
            >
              {{ t.tag_name }}
              <button class="tag-del" @click.stop="askDeleteTag(t.tag_id)" title="删除标签">×</button>
            </span>
          </div>
          <p v-else class="tag-empty-hint">暂无标签，请在上方创建</p>
        </section>

        <!-- 默认角色分配模块 -->
        <section class="action-card">
          <div class="card-title-row">
            <span class="icon-badge" style="--ico: #8b5cf6">
              <svg class="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </span>
            <h3>系统默认分配</h3>
          </div>
          <div class="select-wrap" :class="{ open: dropdownOpen }" ref="selectWrapRef">
            <button class="custom-select" @click="toggleDropdown">
              <span :class="{ placeholder: !defaultRoleName }">{{ defaultRoleName || '-- 请选择基准角色 --' }}</span>
              <svg class="select-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div v-if="dropdownOpen" class="dropdown-menu" :style="{ maxHeight: dropdownMaxHeight + 'px' }">
              <div class="dropdown-item placeholder-item" :class="{ active: !defaultRoleName }" @click="defaultRoleName = ''; dropdownOpen = false">-- 请选择基准角色 --</div>
              <div v-for="r in roles" :key="r.role_id" class="dropdown-item" :class="{ active: defaultRoleName === r.role_name }" @click="defaultRoleName = r.role_name; dropdownOpen = false">{{ r.role_name }}</div>
            </div>
          </div>
          <div v-if="defaultRoleName" class="current-default">
            当前生效：<span class="highlight">{{ defaultRoleName }}</span>
          </div>
        </section>
      </aside>

      <!-- 右侧列表区 -->
      <main class="content-panel">
        <div class="panel-header">
          <h3>角色档案录</h3>
        </div>

        <div v-if="loading" class="loading-state">
          <svg class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          数据加载中...
        </div>

        <div v-else-if="filteredRoles.length === 0" class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
          <p>{{ filterTagId !== null ? '当前筛选条件下无角色数据' : '当前系统无角色数据，请在左侧添加' }}</p>
        </div>

        <!-- 只有此区域允许滚动 -->
        <div v-else class="role-grid-scroll">
          <div class="role-grid">
            <div v-for="(r, idx) in filteredRoles" :key="r.role_id" class="role-card">
              
              <!-- 编辑模式 -->
              <div v-if="editing && editId === r.role_id" class="edit-mode">
                <input v-model="editName" class="edit-input" @keyup.enter="saveEdit" autofocus />
                <div class="edit-tag-row">
                  <label class="edit-tag-label">标签：</label>
                  <div class="edit-tag-multi">
                    <label v-for="t in tags" :key="t.tag_id" class="edit-tag-check">
                      <input type="checkbox" :value="t.tag_id" v-model="editTagIds" />
                      <span :style="{ color: t.tag_color, borderColor: t.tag_color }">{{ t.tag_name }}</span>
                    </label>
                    <span v-if="!tags.length" class="edit-tag-empty">暂无标签</span>
                  </div>
                </div>
                <div class="edit-actions">
                  <button class="btn-icon btn-save" @click="saveEdit" title="保存"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg></button>
                  <button class="btn-icon btn-cancel" @click="cancelEdit" title="取消"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
                </div>
              </div>

              <!-- 展示模式 -->
              <template v-else>
                <div class="role-top">
                  <div class="role-avatar" :style="{ backgroundColor: roleAccent(idx) + '1A', color: roleAccent(idx) }">
                    {{ r.role_name.charAt(0) }}
                  </div>
                  <div class="role-actions">
                    <button class="btn-icon outline" @click="startEdit(r)" title="修改"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg></button>
                    <button class="btn-icon outline danger" @click="deleteRole(r.role_id, r.role_name)" title="删除"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
                  </div>
                </div>
                
                <div class="role-info">
                  <h4 class="role-name" :title="r.role_name">{{ r.role_name }}</h4>
                  <div v-if="(r.tags || []).length" class="role-tag-list">
                    <span v-for="t in r.tags" :key="t.tag_id" class="role-tag-badge" :style="{ '--tag-color': t.tag_color || '#3b82f6' }">{{ t.tag_name }}</span>
                  </div>
                  <p class="role-date">收录于 {{ r.created_at?.slice(0, 10) || '未知时间' }}</p>
                </div>
                
                <div class="role-footer">
                  <div class="staff-badge">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
                    <span>{{ r.staff_count }} 位成员</span>
                  </div>
                </div>
              </template>

            </div>
          </div>
        </div>
      </main>

    </div>

    <!-- 删除标签确认弹窗 -->
    <transition name="modal-fade">
      <div v-if="deleteTagConfirm" class="modal-overlay" @click.self="cancelDeleteTag">
        <div class="modal-card">
          <div class="modal-header">
            <div class="modal-icon">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                <line x1="10" y1="11" x2="10" y2="17"/>
                <line x1="14" y1="11" x2="14" y2="17"/>
              </svg>
            </div>
            <div class="modal-title">删除标签确认</div>
          </div>
          <div class="modal-body">
            <p class="modal-line">确定要删除以下标签吗？</p>
            <div class="modal-tag-preview" :style="{ '--tag-color': deleteTagConfirm.tagColor }">
              <span class="tag-color-dot"></span>
              <span class="tag-name">{{ deleteTagConfirm.tagName }}</span>
            </div>
            <p class="modal-warn">⚠ 关联角色的标签将被一并清除，操作不可恢复。</p>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" @click="cancelDeleteTag">取消</button>
            <button class="btn-danger" @click="confirmDeleteTag">确认删除</button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
/* ================= 基础重置与变量 ================= */
.roles-page {
  --c-bg: #f8fafc;
  --c-surface: #ffffff;
  --c-text-main: #0f172a;
  --c-text-sec: #475569;
  --c-text-muted: #94a3b8;
  --c-border: #e2e8f0;
  --c-border-hover: #cbd5e1;
  --c-primary: #0f172a;
  --c-primary-hover: #1e293b;
  --c-focus: rgba(15,23,42,0.1);
  --c-danger: #ef4444;
  --c-danger-bg: #fef2f2;
  --c-success: #10b981;
  
  height: calc((100vh - 60px) / 0.85);
  display: flex;
  flex-direction: column;
  background-color: var(--c-bg);
  font-family: "Microsoft YaHei", "微软雅黑", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  overflow: hidden; 
}

/* ================= 顶部 Header ================= */
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 28px 0; flex-shrink: 0;
}
.header-left .page-title { margin: 0; font-size: 22px; font-weight: 700; color: var(--c-text-main); letter-spacing: -0.5px; }

.header-stats { display: flex; align-items: center; gap: 12px; }
.stat-card {
  display: flex; align-items: center; gap: 10px;
  background: var(--c-surface); padding: 8px 16px 8px 10px;
  border-radius: 10px; border: 1px solid var(--c-border);
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
.stat-icon {
  width: 34px; height: 34px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--stat-color) 12%, var(--c-surface));
  color: var(--stat-color);
}
.stat-icon svg { width: 16px; height: 16px; }
.stat-body { display: flex; flex-direction: column; }
.stat-val { font-size: 18px; font-weight: 700; color: var(--c-text-main); line-height: 1.2; }
.stat-lbl { font-size: 11px; color: var(--c-text-muted); }

/* ================= 双栏布局 ================= */
.main-layout {
  display: flex; gap: 20px; padding: 16px 28px 20px;
  flex: 1; min-height: 0;
}

/* 左侧栏 */
.side-panel {
  width: 360px; flex-shrink: 0;
  display: flex; flex-direction: column; gap: 12px;
}
.action-card {
  background: var(--c-surface); border-radius: 14px; padding: 18px 20px 20px;
  border: 1px solid var(--c-border);
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  flex: 1;
  display: flex; flex-direction: column;
}

/* 新建角色卡片 — 最近创建列表占满剩余空间 */
.create-role-card { gap: 0; }
.create-role-card .form-group { flex-shrink: 0; }
.create-role-card .status-msg { flex-shrink: 0; }
.recent-role-list {
  flex: 1; display: flex; flex-direction: column; margin-top: 12px; padding-top: 12px;
  min-height: 0; overflow-y: auto;
  border-top: 1px solid color-mix(in srgb, var(--c-border) 70%, transparent);
}
.recent-header {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; font-weight: 600; color: var(--c-text-muted);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; flex-shrink: 0;
}
.recent-count-badge {
  font-size: 10px; font-weight: 500; padding: 0 6px; line-height: 16px; border-radius: 8px;
  background: color-mix(in srgb, var(--c-text-muted) 10%, transparent);
  color: var(--c-text-muted); letter-spacing: 0;
}
.recent-items { display: flex; flex-direction: column; gap: 2px; }
.recent-item {
  display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-radius: 6px;
  transition: background 0.12s; flex-shrink: 0;
}
.recent-item:hover { background: color-mix(in srgb, #3b82f6 6%, var(--c-surface)); }
.recent-avatar {
  width: 20px; height: 20px; border-radius: 6px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 600; line-height: 1;
}
.recent-name { font-size: 13px; color: var(--c-text-main); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-count { font-size: 11px; color: var(--c-text-muted); flex-shrink: 0; }
.card-title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.card-title-row h3 { margin: 0; font-size: 14px; font-weight: 600; color: var(--c-text-main); }
.card-icon { width: 16px; height: 16px; }
.icon-badge {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--ico, #0f172a) 10%, var(--c-surface));
  color: var(--ico, var(--c-text-main));
  border: 1px solid color-mix(in srgb, var(--ico, #0f172a) 22%, var(--c-border));
}
.form-group { display: flex; flex-direction: column; gap: 10px; }
.custom-input {
  width: 100%; padding: 10px 14px; font-size: 14px; color: var(--c-text-main);
  background: var(--c-bg); border: 1px solid var(--c-border); border-radius: 8px;
  outline: none; transition: border-color 0.2s; box-sizing: border-box;
}
.custom-input:focus { border-color: var(--c-text-main); background: var(--c-surface); box-shadow: 0 0 0 3px var(--c-focus); }

.btn-primary {
  padding: 10px 16px; font-size: 14px; font-weight: 400; color: #0f172a;
  background: transparent; border: 1px solid #cbd5e1; border-radius: 8px;
  cursor: pointer; transition: all 0.2s; text-align: center;
}
.btn-primary:hover:not(:disabled) { border-color: #94a3b8; background: rgba(0,0,0,0.02); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.status-msg { margin: 12px 0 0; font-size: 13px; font-weight: 500; color: var(--c-success); display: flex; align-items: center; gap: 4px;}
.status-msg.is-error { color: var(--c-danger); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.select-wrap { position: relative; width: 100%; }
.custom-select {
  width: 100%; padding: 10px 14px; padding-right: 36px; font-size: 14px; color: var(--c-text-main);
  background: var(--c-bg); border: 1px solid var(--c-border); border-radius: 8px;
  cursor: pointer; transition: border-color 0.2s; box-sizing: border-box;
  text-align: left; font-family: inherit; line-height: 1.4;
  display: flex; align-items: center;
}
.custom-select:hover { border-color: var(--c-border-hover); }
.select-wrap.open .custom-select { border-color: #8b5cf6; background: var(--c-surface); }
.select-wrap.open .select-arrow { transform: translateY(-50%) rotate(180deg); }
.custom-select .placeholder { color: var(--c-text-muted); }
.select-arrow { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); width: 16px; height: 16px; color: var(--c-text-muted); pointer-events: none; transition: transform 0.2s; }
.dropdown-menu {
  position: absolute; left: 0; right: 0; top: calc(100% + 4px);
  overflow-y: auto; overflow-x: hidden;
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.08);
  z-index: 100; padding: 4px 0;
  scrollbar-width: thin;
  scrollbar-color: #94a3b8 transparent;
}
.dropdown-menu::-webkit-scrollbar { width: 6px; }
.dropdown-menu::-webkit-scrollbar-track { background: transparent; margin: 4px 0; }
.dropdown-menu::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
.dropdown-menu::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
.dropdown-item {
  padding: 8px 14px; font-size: 13px; color: var(--c-text-main); cursor: pointer;
  transition: background 0.1s; user-select: none;
}
.dropdown-item:hover { background: color-mix(in srgb, #8b5cf6 8%, var(--c-surface)); }
.dropdown-item.active { background: color-mix(in srgb, #8b5cf6 12%, var(--c-surface)); color: #8b5cf6; font-weight: 500; }
.dropdown-item.placeholder-item { color: var(--c-text-muted); font-style: italic; }
.current-default { margin-top: 14px; font-size: 13px; color: var(--c-text-sec); background: var(--c-bg); padding: 8px 12px; border-radius: 6px; }
.current-default .highlight { font-weight: 600; color: var(--c-text-main); }


/* ================= 右侧内容与网格 ================= */
.content-panel {
  flex: 1; min-width: 0; 
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 14px;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
.panel-header { padding: 14px 22px; border-bottom: 1px solid var(--c-border); flex-shrink: 0;}
.panel-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: var(--c-text-main); }

/* 仅允许网格区域滚动 */
.role-grid-scroll {
  flex: 1; overflow-y: auto; overflow-x: hidden; padding: 16px;
}
/* 定制细长滚动条 */
.role-grid-scroll::-webkit-scrollbar { width: 6px; }
.role-grid-scroll::-webkit-scrollbar-track { background: transparent; }
.role-grid-scroll::-webkit-scrollbar-thumb { background: var(--c-border-hover); border-radius: 4px; }
.role-grid-scroll::-webkit-scrollbar-thumb:hover { background: var(--c-text-muted); }

.role-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(185px, 1fr)); gap: 12px; align-content: start; }

/* 角色卡片 (工牌式样) */
.role-card {
  border: 1px solid var(--c-border); border-radius: 10px; padding: 12px;
  display: flex; flex-direction: column; gap: 10px;
  background: var(--c-surface); transition: border-color 0.2s, box-shadow 0.2s;
}
.role-card:hover { border-color: var(--c-border-hover); box-shadow: 0 4px 12px rgba(0,0,0,0.03); }

.role-top { display: flex; justify-content: space-between; align-items: flex-start; }
.role-avatar {
  width: 44px; height: 44px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 600;
}
.role-actions { display: flex; gap: 6px; opacity: 0; transition: opacity 0.2s; }
.role-card:hover .role-actions { opacity: 1; }

.btn-icon {
  width: 28px; height: 28px; border-radius: 6px; border: none; background: transparent;
  display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--c-text-sec); transition: all 0.2s;
}
.btn-icon.outline { border: 1px solid var(--c-border); background: var(--c-surface); }
.btn-icon.outline:hover { border-color: var(--c-text-main); color: var(--c-text-main); }
.btn-icon.outline.danger:hover { border-color: var(--c-danger); color: var(--c-danger); background: var(--c-danger-bg); }
.btn-icon svg { width: 14px; height: 14px; }

.role-info { display: flex; flex-direction: column; gap: 4px; }
.role-name { margin: 0; font-size: 15px; font-weight: 600; color: var(--c-text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.role-date { margin: 0; font-size: 12px; color: var(--c-text-muted); }

/* 角色标签徽标 */
.role-tag-badge {
  display: inline-block; font-size: 11px; font-weight: 500; padding: 1px 8px;
  border-radius: 10px; width: fit-content;
  background: color-mix(in srgb, var(--tag-color) 14%, var(--c-surface));
  color: var(--tag-color);
  border: 1px solid color-mix(in srgb, var(--tag-color) 25%, var(--c-border));
}
.role-tag-list { display: flex; flex-wrap: wrap; gap: 4px; }

/* ================= 标签管理 ================= */
.tag-input-row { display: flex; flex-direction: column; gap: 6px; }
.color-picker-row { display: flex; flex-wrap: wrap; gap: 4px; }
.color-dot {
  width: 18px; height: 18px; border-radius: 50%; border: 2px solid transparent;
  cursor: pointer; padding: 0; transition: border-color 0.15s; flex-shrink: 0;
}
.color-dot:hover { border-color: var(--c-text-muted); }
.color-dot.active { border-color: var(--c-text-main); box-shadow: 0 0 0 1px var(--c-surface); }

.tag-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.tag-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; font-weight: 500; padding: 3px 10px; border-radius: 20px;
  cursor: pointer; user-select: none; transition: all 0.15s;
  background: color-mix(in srgb, var(--tag-color) 14%, var(--c-surface));
  color: var(--tag-color);
  border: 1px solid color-mix(in srgb, var(--tag-color) 25%, var(--c-border));
}
.tag-badge:hover { background: color-mix(in srgb, var(--tag-color) 22%, var(--c-surface)); }
.tag-badge.active {
  background: color-mix(in srgb, var(--tag-color) 100%, var(--c-surface));
  color: #fff; border-color: var(--tag-color);
}
.tag-del {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; font-size: 12px; line-height: 1;
  border: none; background: transparent; color: inherit; opacity: 0.5;
  cursor: pointer; padding: 0; border-radius: 50%;
}
.tag-del:hover { opacity: 1; }
.tag-empty-hint { margin: 12px 0 0; font-size: 12px; color: var(--c-text-muted); }

/* 编辑模式标签选择 */
.edit-tag-row { display: flex; align-items: flex-start; gap: 8px; }
.edit-tag-label { font-size: 13px; color: var(--c-text-sec); white-space: nowrap; padding-top: 4px; }
.edit-tag-multi { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.edit-tag-check {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; font-weight: 500; padding: 2px 8px; border-radius: 10px;
  background: var(--c-bg); cursor: pointer; user-select: none;
}
.edit-tag-check input { margin: 0; accent-color: var(--c-text-main); }
.edit-tag-check span {
  padding: 1px 4px; border-radius: 8px; border: 1px solid;
  background: color-mix(in srgb, currentColor 10%, transparent);
}
.edit-tag-empty { font-size: 12px; color: var(--c-text-muted); }

.role-footer { padding-top: 14px; border-top: 1px dashed var(--c-border); }
.staff-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500; color: var(--c-text-sec);
  background: var(--c-bg); padding: 4px 10px; border-radius: 20px;
}
.staff-badge svg { width: 12px; height: 12px; }

/* 编辑状态 */
.edit-mode { display: flex; flex-direction: column; gap: 12px; height: 100%; justify-content: center;}
.edit-input { padding: 8px 12px; border: 1px solid var(--c-text-main); border-radius: 6px; font-size: 14px; outline: none; }
.edit-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn-save { background: var(--c-text-main); color: #fff; }
.btn-save:hover { background: var(--c-primary-hover); }
.btn-cancel { background: var(--c-bg); color: var(--c-text-sec); }
.btn-cancel:hover { background: var(--c-border); }

/* 状态提示 */
.loading-state, .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--c-text-muted); font-size: 14px; gap: 12px; }
.empty-state svg { width: 48px; height: 48px; color: var(--c-border); }
.spin { width: 24px; height: 24px; animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* 响应式 */
@media (max-width: 1024px) {
  .main-layout { flex-direction: column; overflow-y: auto; }
  .side-panel { width: 100%; flex-direction: row; flex-wrap: wrap; }
  .action-card { flex: 1; min-width: 300px; }
  .roles-page { height: auto; min-height: 100vh; overflow: visible; }
  .content-panel { flex: none; height: 600px; } /* 在小屏幕上固定高度让内部滚动 */
}

/* ================= 删除标签确认弹窗 ================= */
.modal-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.modal-card {
  background: var(--c-surface);
  border-radius: 14px;
  width: 100%; max-width: 380px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.18);
  overflow: hidden;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.modal-header {
  display: flex; align-items: center; gap: 12px;
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--c-border);
}
.modal-icon {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, #ef4444 12%, var(--c-surface));
  color: #ef4444;
}
.modal-title {
  font-size: 15px; font-weight: 600; color: var(--c-text-main);
}
.modal-body { padding: 18px 22px; }
.modal-line {
  margin: 0 0 12px 0; font-size: 13px; color: var(--c-text-muted);
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.modal-tag-preview {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px; border-radius: 8px;
  background: color-mix(in srgb, var(--tag-color) 12%, var(--c-surface));
  border: 1px solid color-mix(in srgb, var(--tag-color) 28%, var(--c-border));
  font-size: 13px; font-weight: 500; color: var(--c-text-main);
  margin-bottom: 12px;
}
.modal-tag-preview .tag-color-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--tag-color);
}
.modal-warn {
  margin: 0; font-size: 12px; color: #b45309;
  background: color-mix(in srgb, #f59e0b 8%, var(--c-surface));
  border-left: 2px solid #f59e0b;
  padding: 6px 10px; border-radius: 4px;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.modal-footer {
  display: flex; gap: 10px; justify-content: flex-end;
  padding: 14px 22px 18px;
  border-top: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-text-muted) 3%, var(--c-surface));
}
.btn-secondary, .btn-danger {
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  font-size: 13px; font-weight: 400;
  padding: 7px 18px; border-radius: 8px; cursor: pointer;
  transition: all 0.15s; min-width: 80px;
}
.btn-secondary {
  background: var(--c-surface);
  border: 1px solid #cbd5e1;
  color: #0f172a;
}
.btn-secondary:hover { border-color: #94a3b8; background: #f8fafc; }
.btn-danger {
  background: #ef4444; border: 1px solid #ef4444; color: #fff;
}
.btn-danger:hover { background: #dc2626; border-color: #dc2626; }

.modal-fade-enter-active, .modal-fade-leave-active {
  transition: opacity 0.18s ease;
}
.modal-fade-enter-active .modal-card, .modal-fade-leave-active .modal-card {
  transition: transform 0.18s ease, opacity 0.18s ease;
}
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
.modal-fade-enter-from .modal-card, .modal-fade-leave-to .modal-card {
  transform: scale(0.96); opacity: 0;
}
</style>