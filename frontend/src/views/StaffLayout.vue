<script setup lang="ts">
/**
 * StaffLayout.vue — 人员管理外层布局
 * 与 TicketsLayout 保持相同风格：左侧深蓝可折叠侧边栏 + 右侧白底主内容区
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const collapsed = ref(false)
function toggleCollapse() { collapsed.value = !collapsed.value }

const menuItems = [
  { key: 'list', label: '人员档案查询', icon: 'people', path: '/staff' },
  { key: 'schedule', label: '值班排班管理', icon: 'calendar', path: '/staff/schedule' },
  { key: 'roles', label: '岗位角色配置', icon: 'shield', path: '/staff/roles' },
]

const activeKey = computed(() => {
  if (route.path === '/staff/schedule') return 'schedule'
  if (route.path === '/staff/roles') return 'roles'
  return 'list'
})

function goMenu(path: string) { router.push(path) }
</script>

<template>
  <div class="staff-layout">
    <aside class="sidebar" :class="{ collapsed }">
      <div class="sidebar-header" @click="toggleCollapse">
        <svg class="sidebar-logo" viewBox="0 0 32 32" fill="none">
          <rect width="32" height="32" rx="6" fill="#fff" opacity="0.2"/>
          <circle cx="16" cy="11" r="4" fill="#fff" opacity="0.9"/>
          <ellipse cx="16" cy="24" rx="8" ry="5" fill="#fff" opacity="0.6"/>
        </svg>
        <span class="sidebar-title" v-show="!collapsed">人员管理</span>
        <svg class="collapse-btn" :class="{ rotated: collapsed }" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
        </svg>
      </div>
      <nav class="sidebar-nav">
        <div v-for="item in menuItems" :key="item.key"
          class="menu-item" :class="{ active: activeKey === item.key, collapsed }"
          @click="goMenu(item.path)">
          <svg v-if="item.icon === 'people'" class="menu-icon" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
            <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/>
          </svg>
          <svg v-else-if="item.icon === 'calendar'" class="menu-icon" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
            <path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM9 10H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2z"/>
          </svg>
          <svg v-else-if="item.icon === 'shield'" class="menu-icon" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
            <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/>
          </svg>
          <span class="menu-label" v-show="!collapsed">{{ item.label }}</span>
        </div>
      </nav>
    </aside>
    <main class="staff-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.staff-layout {
  display: flex;
  min-height: calc((100vh - 60px) / 0.85);
  background: #f5f7fa;
}
.sidebar {
  width: 220px;
  background: linear-gradient(180deg, #001529 0%, #002140 100%);
  display: flex; flex-direction: column;
  transition: width 0.25s ease;
  flex-shrink: 0; overflow: hidden;
}
.sidebar.collapsed { width: 60px; }
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
  display: flex; align-items: center; gap: 10px;
  padding: 16px 14px; cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.sidebar-logo { width: 28px; height: 28px; flex-shrink: 0; }
.sidebar-title { color: #fff; font-size: 15px; font-weight: 600; white-space: nowrap; flex: 1; }
.collapse-btn { color: rgba(255,255,255,0.5); flex-shrink: 0; transition: transform 0.25s; }
.collapse-btn.rotated { transform: rotate(180deg); }
.sidebar-nav { flex: 1; padding: 8px 0; }
.menu-item {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 18px; cursor: pointer;
  color: rgba(255,255,255,0.65); font-size: 14px;
  transition: all 0.2s;
  border-left: 3px solid transparent; white-space: nowrap;
}
.menu-item:hover { color: #fff; background: rgba(255,255,255,0.06); }
.menu-item.active {
  color: #fff; background: rgba(24,144,255,0.15);
  border-left-color: #1890ff; font-weight: 600;
}
.menu-item.collapsed { padding: 12px; justify-content: center; }
.menu-icon { flex-shrink: 0; opacity: 0.85; display: block; }
.menu-label { flex: 1; }
.staff-main { flex: 1; overflow-y: auto; padding: 20px 24px; background: #f5f7fa; }
</style>
