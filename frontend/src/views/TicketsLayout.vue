<script setup lang="ts">
/**
 * TicketsLayout.vue — 工单管理外层布局
 * 左侧深蓝侧边栏（可折叠） + 右侧白底主内容区
 * 语音控制预留：监听 focus-assistant 事件，自动切到对应菜单
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

// ========== 侧边栏折叠 ==========
const collapsed = ref(false)
function toggleCollapse() {
  collapsed.value = !collapsed.value
}

// ========== 菜单定义 ==========
const menuItems = [
  { key: 'list', label: '工单列表查询', icon: 'list', path: '/tickets' },
  { key: 'stats', label: '工单统计看板', icon: 'chart', path: '/tickets/stats' },
  { key: 'config', label: '工单参数配置', icon: 'setting', path: '/tickets/config' },
]

const activeKey = computed(() => {
  if (route.path === '/tickets/stats') return 'stats'
  if (route.path === '/tickets/config') return 'config'
  return 'list'
})

function goMenu(path: string) {
  router.push(path)
}

// ========== 语音联动预留 ==========
function onVoiceNav(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.target) {
    const item = menuItems.find(m => m.path === detail.target)
    if (item) goMenu(item.path)
  }
}
onMounted(() => window.addEventListener('voice-nav', onVoiceNav))
onUnmounted(() => window.removeEventListener('voice-nav', onVoiceNav))
</script>

<template>
  <div class="tickets-layout">
    <!-- 深蓝色侧边栏 -->
    <aside class="sidebar" :class="{ collapsed }">
      <div class="sidebar-header" @click="toggleCollapse">
        <svg class="sidebar-logo" viewBox="0 0 32 32" fill="none">
          <rect width="32" height="32" rx="6" fill="#fff" opacity="0.2"/>
          <path d="M9 21V11l7 5.5L9 21z" fill="#fff" opacity="0.9"/>
          <path d="M16 16.5v-5.5l7 5.5-7 5.5v-5.5z" fill="#fff" opacity="0.6"/>
        </svg>
        <span class="sidebar-title" v-show="!collapsed">工单管理</span>
        <svg class="collapse-btn" :class="{ rotated: collapsed }" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
        </svg>
      </div>
      <nav class="sidebar-nav">
        <div
          v-for="item in menuItems"
          :key="item.key"
          class="menu-item"
          :class="{ active: activeKey === item.key, collapsed }"
          @click="goMenu(item.path)"
        >
          <!-- 图标 -->
          <svg v-if="item.icon === 'list'" class="menu-icon" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
            <path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-1 9H9V9h10v2zm-4 4H9v-2h6v2zm4-8H9V5h10v2z"/>
          </svg>
          <svg v-else-if="item.icon === 'chart'" class="menu-icon" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
            <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/>
          </svg>
          <svg v-else-if="item.icon === 'setting'" class="menu-icon" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
            <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
          </svg>
          <span class="menu-label" v-show="!collapsed">{{ item.label }}</span>
        </div>
      </nav>
    </aside>

    <!-- 右侧主内容区 -->
    <main class="tickets-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.tickets-layout {
  display: flex;
  min-height: calc((100vh - 60px) / 0.85); /* 减去 App.vue 顶栏高度 */
  background: #f5f7fa;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: 220px;
  background: linear-gradient(180deg, #001529 0%, #002140 100%);
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease;
  flex-shrink: 0;
  overflow: hidden;
}
.sidebar.collapsed {
  width: 60px;
}
.sidebar.collapsed .sidebar-header {
  justify-content: center;
  padding: 16px 8px;
  position: relative;
}
.sidebar.collapsed .collapse-btn {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 1;
}
.sidebar.collapsed .collapse-btn.rotated {
  transform: translateY(-50%) rotate(180deg);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 14px;
  cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.sidebar-logo {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}
.sidebar-title {
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  flex: 1;
}
.collapse-btn {
  color: rgba(255,255,255,0.5);
  flex-shrink: 0;
  transition: transform 0.25s;
}
.collapse-btn.rotated {
  transform: rotate(180deg);
}

/* ===== 菜单 ===== */
.sidebar-nav {
  flex: 1;
  padding: 8px 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  cursor: pointer;
  color: rgba(255,255,255,0.65);
  font-size: 14px;
  transition: all 0.2s;
  border-left: 3px solid transparent;
  white-space: nowrap;
}
.menu-item:hover {
  color: #fff;
  background: rgba(255,255,255,0.06);
}
.menu-item.active {
  color: #fff;
  background: rgba(24,144,255,0.15);
  border-left-color: #1890ff;
  font-weight: 600;
}
.menu-item.collapsed {
  padding: 12px;
  justify-content: center;
}

.menu-icon {
  flex-shrink: 0;
  opacity: 0.85;
  display: block;
}

.menu-label {
  flex: 1;
}

/* ===== 主内容区 ===== */
.tickets-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  background: #f5f7fa;
  position: relative;
  z-index: 1;
}
</style>
