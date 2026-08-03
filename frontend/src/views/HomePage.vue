<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { useTicketStore } from '../stores/ticketStore'
import { useActivityLog } from '../stores/activityLog'

// ========== 路由 & Store ==========
const router = useRouter()
const ticketStore = useTicketStore()
const { logs: activityLogs } = useActivityLog()

// ========== 定时刷新数据 ==========
let refreshTimer: ReturnType<typeof setInterval> | null = null

// ========== KPI 卡片数据（渐变色 + 圆形图标 + 点击跳列表带筛选）==========
const kpiCards = computed(() => [
  {
    label: '总工单数',
    value: ticketStore.stat.total,
    filterKey: null,
    path: 'M3 3h18v18H3V3zm14 14V7H7v10h10zm-2-2H9v-2h6v2zm0-4H9V9h6v2z',
    gradient: 'linear-gradient(135deg, #00d2d3 0%, #0a7e8c 100%)',
    glow: 'rgba(10, 126, 140, 0.3)',
  },
  {
    label: '未完成工单',
    value: ticketStore.stat.pending,
    filterKey: '未完成',
    path: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
    gradient: 'linear-gradient(135deg, #8E2DE2 0%, #4A00E0 100%)',
    glow: 'rgba(142, 45, 226, 0.3)',
  },
  {
    label: '高优先级',
    value: ticketStore.stat.high,
    filterKey: 'priority=高',
    path: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
    gradient: 'linear-gradient(135deg, #F2994A 0%, #F2C94C 100%)',
    glow: 'rgba(242, 153, 74, 0.3)',
  },
  {
    label: '已完成',
    value: ticketStore.stat.done,
    filterKey: '已完成',
    path: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
    gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    glow: 'rgba(102, 126, 234, 0.3)',
  },
])

function goToTicketList(filterKey: string | null) {
  if (!filterKey) {
    router.push('/tickets')
    return
  }
  if (filterKey.startsWith('priority=')) {
    router.push({ path: '/tickets', query: { filterPriority: filterKey.replace('priority=', '') } })
  } else {
    router.push({ path: '/tickets', query: { filterStatus: filterKey } })
  }
}

// 待办预警：高优先级且未完成的工单，计算真实超时
const urgentList = computed(() => {
  return ticketStore.urgentTickets
    .filter((t: any) => t.status !== '已完成')
    .slice(0, 8)
    .map((t: any) => {
      const created = new Date(t.create_time)
      const hours = Math.floor((Date.now() - created.getTime()) / 3600000)
      return { ...t, overdueHours: hours }
    })
})

function deadlineText(hours: number, index: number): string {
  if (hours > 72) return `超期 ${Math.floor(hours / 24)}d`
  if (hours > 4) return `超期 ${hours}h`
  return `剩 ${4 - hours}h`
}

function deadlineClass(hours: number): string {
  return hours > 4 ? 'over' : ''
}

// ========== 快捷入口 ==========
const quickLinks = [
  { label: '工单列表', path: '/tickets', pathData: 'M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-1 9H9V9h10v2zm-4 4H9v-2h6v2zm4-8H9V5h10v2z' },
  { label: '监控大屏', path: '/monitor', pathData: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z' },
  { label: '语音助手', path: '__voice__', pathData: 'M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z' }
]
function goTo(path: string) {
  if (path === '__voice__') {
    window.dispatchEvent(new CustomEvent('focus-assistant'))
    return
  }
  router.push(path)
}

const notices = [
  '【公告】系统已全面升级，支持实时数据监控与智能预警',
  '【提醒】高优先级工单请于4小时内响应处理',
  '【说明】点击首页KPI卡片可快速跳转至对应工单列表',
]

const statusMap: Record<string, { color: string }> = {
  success: { color: '#52c41a' },
  warning: { color: '#faad14' },
  info: { color: '#1890ff' },
}

// ========== 人员工单负荷（基于真实数据） ==========
const assigneeLoad = computed(() => {
  const map: Record<string, { total: number; urgent: number }> = {}
  for (const t of ticketStore.tickets as any[]) {
    if (!map[t.assignee]) map[t.assignee] = { total: 0, urgent: 0 }
    map[t.assignee].total++
    if (t.priority === '高' && t.status !== '已完成') map[t.assignee].urgent++
  }
  return Object.entries(map)
    .map(([name, val]) => ({ name, ...val }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 8)
})

// ========== ECharts 图表1：工单状态流转 ==========
const chartRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

function initChart() {
  if (!chartRef.value) return
  chartInstance = echarts.init(chartRef.value)
  updateChart()
}

function updateChart() {
  if (!chartInstance) return
  const list = ticketStore.tickets
  const done = list.filter((t: any) => t.status === '已完成').length
  const pending = list.filter((t: any) => t.status === '未完成').length
  const inProgress = list.filter((t: any) => t.status === '进行中').length

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#e8e8e8',
      padding: [10, 16],
      textStyle: { color: '#333', fontSize: 13 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-radius: 4px;',
    },
    grid: { left: '3%', right: '4%', top: '15%', bottom: '5%', containLabel: true },
    xAxis: {
      type: 'category',
      data: ['已完成', '未完成', '进行中'],
      axisLabel: { color: '#333333', fontSize: 13, margin: 12, fontWeight: 500 },
      axisTick: { show: true, lineStyle: { color: '#94a3b8' } },
      axisLine: { show: true, lineStyle: { color: '#64748b', width: 1.2 } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#8c8c8c', fontSize: 12 },
      axisTick: { show: true, lineStyle: { color: '#94a3b8' } },
      axisLine: { show: true, lineStyle: { color: '#64748b', width: 1.2 } },
      splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
      splitArea: {
        show: true,
        areaStyle: {
          color: ['rgba(255,255,255,1)', 'rgba(0,0,0,0.015)'],
        },
      },
    },
    series: [
      {
        name: '工单数量',
        type: 'bar',
        barWidth: '25%',
        data: [
          { value: done, itemStyle: { color: '#a78bfa' } },
          { value: pending, itemStyle: { color: '#fb923c' } },
          { value: inProgress, itemStyle: { color: '#67e8f9' } },
        ],
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: {
          show: true,
          position: 'inside',
          color: '#ffffff',
          fontSize: 15,
          fontFamily: 'Microsoft YaHei, 微软雅黑, sans-serif',
          fontWeight: 'normal',
          distance: 0,
          formatter: (p: any) => p.value > 0 ? p.value : '',
        },
      },
    ],
  }
  chartInstance.setOption(option)
}

// 确保 watch 依赖完整的 tickets 变化来刷新图表
watch(() => ticketStore.tickets, updateChart, { deep: true })

function handleResize() { 
  chartInstance?.resize()
  workloadChartInstance?.resize() 
}

// ========== ECharts 图表2：人员工单负荷 ==========
const workloadChartRef = ref<HTMLDivElement | null>(null)
let workloadChartInstance: echarts.ECharts | null = null

function initWorkloadChart() {
  if (!workloadChartRef.value) return
  workloadChartInstance = echarts.init(workloadChartRef.value)
  updateWorkloadChart()
}

function updateWorkloadChart() {
  if (!workloadChartInstance) return
  const data = assigneeLoad.value
  workloadChartInstance.setOption({
    color: ['#60a5fa', '#fb7185'], 
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#e8e8e8',
      padding: [10, 16],
      textStyle: { color: '#333', fontSize: 13 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-radius: 4px;',
    },
    legend: {
      data: ['总工单', '紧急工单'],
      right: '4%',
      top: '0%',
      icon: 'circle',
      textStyle: { color: '#333', fontSize: 13, fontWeight: 500 },
    },
    grid: { left: '3%', right: '4%', bottom: '5%', top: '15%', containLabel: true },
    xAxis: {
      type: 'category',
      data: data.length ? data.map(d => d.name) : ['暂无数据'],
      axisLabel: { color: '#333333', fontSize: 13, margin: 12, fontWeight: 500 },
      axisTick: { show: true, lineStyle: { color: '#94a3b8' } },
      axisLine: { show: true, lineStyle: { color: '#64748b', width: 1.2 } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#8c8c8c', fontSize: 12 },
      axisTick: { show: true, lineStyle: { color: '#94a3b8' } },
      axisLine: { show: true, lineStyle: { color: '#64748b', width: 1.2 } },
      splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
      splitArea: {
        show: true,
        areaStyle: {
          color: ['rgba(255,255,255,1)', 'rgba(0,0,0,0.015)'],
        },
      },
    },
    series: [
      {
        name: '总工单',
        type: 'bar',
        barWidth: 36,
        barGap: '20%',
        data: data.map(d => d.total),
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'inside', color: '#ffffff', fontSize: 13, fontFamily: 'Microsoft YaHei, 微软雅黑, sans-serif', fontWeight: 'normal', formatter: (p: any) => p.value > 0 ? p.value : '' },
      },
      {
        name: '紧急工单',
        type: 'bar',
        barWidth: 36,
        data: data.map(d => d.urgent),
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'inside', color: '#ffffff', fontSize: 13, fontFamily: 'Microsoft YaHei, 微软雅黑, sans-serif', fontWeight: 'normal', formatter: (p: any) => p.value > 0 ? p.value : '' },
      },
    ],
  })
}

// 监听真实负荷数据变化
watch(assigneeLoad, updateWorkloadChart, { deep: true })

// ========== 最新操作日志自动轮播 ==========
const logBodyRef = ref<HTMLDivElement | null>(null)
let logScrollTimer: ReturnType<typeof setInterval> | null = null
let logScrollPaused = false

function startLogAutoScroll() {
  stopLogAutoScroll()
  logScrollTimer = setInterval(() => {
    if (logScrollPaused || !logBodyRef.value) return
    const el = logBodyRef.value
    const firstChild = el.children[0] as HTMLElement | undefined
    if (!firstChild) return
    const itemHeight = firstChild.offsetHeight || 48
    // 如果滚动到底部，平滑回到顶部
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - itemHeight) {
      el.scrollTo({ top: 0, behavior: 'smooth' })
    } else {
      el.scrollBy({ top: itemHeight, behavior: 'smooth' })
    }
  }, 3000)
}

function stopLogAutoScroll() {
  if (logScrollTimer) { clearInterval(logScrollTimer); logScrollTimer = null }
}

function pauseAutoScroll() { logScrollPaused = true }
function resumeAutoScroll() { logScrollPaused = false }

// ========== 待办预警列表自动滚动（CSS 动画）==========
const urgentScrollPaused = ref(false)

onMounted(() => {
  ticketStore.fetchTickets()
  initChart()
  initWorkloadChart()
  window.addEventListener('resize', handleResize)
  // 每30秒自动刷新
  refreshTimer = setInterval(() => ticketStore.fetchTickets(), 30000)
  // 启动操作日志自动轮播
  startLogAutoScroll()
})
onUnmounted(() => {
  chartInstance?.dispose()
  chartInstance = null
  workloadChartInstance?.dispose()
  workloadChartInstance = null
  window.removeEventListener('resize', handleResize)
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  stopLogAutoScroll()
})
</script>

<template>
  <div class="home-page">
    <div class="kpi-grid">
      <div
        v-for="card in kpiCards"
        :key="card.label"
        class="kpi-card"
        :style="{ background: card.gradient, boxShadow: `0 4px 12px ${card.glow}` }"
        @click="goToTicketList(card.filterKey)"
        :title="card.filterKey ? `点击查看「${card.label}」的工单` : '点击查看所有工单'"
      >
        <div class="card-icon-wrapper">
          <svg class="card-icon" viewBox="0 0 24 24" fill="currentColor">
            <path :d="card.path" />
          </svg>
        </div>
        <div class="card-text-wrapper">
          <span class="card-value">{{ card.value }}</span>
          <span class="card-label">{{ card.label }}</span>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <!-- 左侧：图表区（上下两张卡） -->
      <div class="left-col">
        <div class="card chart-card">
          <div class="card-head" style="--accent: #1890ff;">
            <span class="card-head-title">工单状态流转分析</span>
          </div>
          <div class="card-body chart-body">
            <div ref="chartRef" class="chart-fill"></div>
          </div>
        </div>

        <div class="card chart-card">
          <div class="card-head" style="--accent: #722ed1;">
            <span class="card-head-title">人员工单负荷分析</span>
          </div>
          <div class="card-body chart-body">
            <div ref="workloadChartRef" class="chart-fill"></div>
          </div>
        </div>
      </div>

      <!-- 右侧：信息面板 -->
      <div class="side-col">
        <div class="card urgent-card">
          <div class="card-head" style="--accent: #f5222d;">
            <span class="card-head-title">待办预警</span>
            <span class="badge">{{ urgentList.length }}</span>
          </div>
          <div class="card-body">
            <div v-if="urgentList.length" class="urgent-scroll-container" @mouseenter="urgentScrollPaused = true" @mouseleave="urgentScrollPaused = false">
              <div class="urgent-scroll-wrap" :class="{ paused: urgentScrollPaused }">
                <ul class="urgent-list">
                  <li v-for="(t, i) in urgentList" :key="t.id" class="urgent-row">
                    <span class="tag-urgent">紧急</span>
                    <span class="urgent-text">{{ t.title }}</span>
                  </li>
                </ul>
                <ul class="urgent-list" aria-hidden="true">
                  <li v-for="(t, i) in urgentList" :key="'cp-' + t.id" class="urgent-row">
                    <span class="tag-urgent">紧急</span>
                    <span class="urgent-text">{{ t.title }}</span>
                  </li>
                </ul>
              </div>
            </div>
            <div v-else class="empty">暂无高优先级待办</div>
          </div>
        </div>

        <div class="card">
          <div class="card-head" style="--accent: #722ed1;">
            <span class="card-head-title">常用功能</span>
          </div>
          <div class="quick-row">
            <button v-for="lk in quickLinks" :key="lk.path" class="quick-btn" @click="goTo(lk.path)">
              <svg class="quick-icon" viewBox="0 0 24 24" fill="currentColor">
                <path :d="lk.pathData" />
              </svg>
              <span class="quick-label">{{ lk.label }}</span>
            </button>
          </div>
          <div class="split-line"></div>
          <div class="card-head" style="--accent: #13c2c2; border-top: none;">
            <span class="card-head-title">系统公告</span>
          </div>
          <div class="notice-list">
            <p v-for="(n, i) in notices" :key="i" class="notice-line">{{ n }}</p>
          </div>
        </div>

        <div class="card">
          <div class="card-head" style="--accent: #52c41a;">
            <span class="card-head-title">最新操作日志</span>
          </div>
          <div ref="logBodyRef" class="log-body" @mouseenter="pauseAutoScroll" @mouseleave="resumeAutoScroll">
            <div v-for="log in activityLogs" :key="log.time" class="log-row">
              <span class="log-dot"></span>
              <span class="log-text"><strong>{{ log.user }}</strong> {{ log.action }}</span>
              <span class="log-time">{{ log.time }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  height: calc((100vh - 60px) / 0.85);
  padding: 12px 16px;
  background: #f0f2f5;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* KPI 模块 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 12px;
  flex-shrink: 0;
}
.kpi-card {
  border-radius: 12px;
  padding: 28px 18px;
  color: #ffffff;
  display: flex;
  align-items: center;
  cursor: pointer;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.kpi-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.12);
}
.card-icon-wrapper {
  width: 48px;
  height: 48px;
  margin-right: 16px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 50%;
  flex-shrink: 0;
}
.card-icon {
  width: 26px;
  height: 26px;
  color: #ffffff;
}
.card-text-wrapper {
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.card-value {
  font-size: 30px;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.2;
  letter-spacing: 0.5px;
}
.card-label {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.85);
  margin-top: 4px;
  letter-spacing: 0.2px;
}
@media (max-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .home-page { padding: 12px 4px; }
  .kpi-grid { grid-template-columns: 1fr; gap: 8px; }
}

/* 主体网格布局 — 占满剩余高度 */
.content-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
}
.side-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

/* 严谨统一的卡片容器 */
.card {
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
  display: flex;
  flex-direction: column;
}
.left-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}
.chart-card {
  flex: 1;
  min-height: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #f0f0f0;
  position: relative;
}
.card-head::before {
  content: '';
  position: absolute;
  left: 20px;
  width: 3px;
  height: 16px;
  background: var(--accent);
  border-radius: 2px;
}
.card-head-title {
  font-size: 16px; /* 标题字号加大 */
  font-weight: 600;
  color: #262626;
  padding-left: 12px;
}
.card-body {
  padding: 16px 20px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.chart-body {
  flex: 1;
  min-height: 0;
  padding: 0;
}
.chart-fill {
  width: 100%;
  height: 100%;
  min-height: 0;
}

/* 侧边栏卡片高度分配 */
.side-col .card:first-child {
  flex: 1.4;
  min-height: 0;
}
.side-col .card.urgent-card {
  flex: 1.8;
  min-height: 0;
}
.side-col .card:last-child {
  flex: 1;
  min-height: 0;
}

/* UI 组件与文本控制 */
.badge {
  background: #f5222d;
  color: #fff;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
}
.urgent-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.urgent-scroll-container {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.urgent-scroll-wrap {
  display: flex;
  flex-direction: column;
  animation: urgentScroll 120s linear infinite;
}
.urgent-scroll-wrap.paused {
  animation-play-state: paused;
}
@keyframes urgentScroll {
  0% { transform: translateY(0); }
  100% { transform: translateY(-50%); }
}
.urgent-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px dashed #f0f0f0;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.urgent-row:last-child { border-bottom: none; }
.tag-urgent {
  background: #fff1f0;
  color: #f5222d;
  border: 1px solid #ffa39e;
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  white-space: nowrap;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.urgent-text {
  font-size: 12px;
  color: #333333;
  font-weight: 400;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.urgent-deadline {
  font-size: 13px; /* 【修改点】字号调大 */
  color: #8c8c8c;
  white-space: nowrap;
}
.urgent-deadline.over { color: #f5222d; font-weight: 600; }
.empty {
  text-align: center;
  color: #bfbfbf;
  font-size: 14px;
  padding: 24px 0;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.quick-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 16px 20px;
}
.quick-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 0;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
  color: #333333;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.quick-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
  background: #f0f8ff; /* 悬停颜色调整 */
}
.quick-icon {
  width: 24px;
  height: 24px;
}
.quick-label {
  font-size: 13px;
}
.split-line {
  height: 1px;
  background: #f0f0f0;
  margin: 0 20px;
}

.notice-list {
  padding: 0 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px; /* 间距拉开 */
}
.notice-line {
  margin: 0;
  font-size: 14px; /* 【修改点】字号加大，颜色加深 */
  color: #333333;
  line-height: 1.6;
  position: relative;
  padding-left: 14px;
}
.notice-line::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 6px;
  height: 6px;
  background: #94a3b8;
  border-radius: 50%;
}

.log-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 12px 8px 20px;
  scroll-behavior: smooth;
}
.log-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
  flex-shrink: 0;
}
.log-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px dashed #f0f0f0;
}
.log-row:last-child { border-bottom: none; }
.log-text {
  flex: 1;
  font-size: 14px; /* 【修改点】字号加大，更清晰 */
  color: #333333; /* 【修改点】颜色加深 */
}
.log-text strong {
  color: #111111; /* 强调用户名更加突出 */
  font-weight: 600;
}
.log-time {
  font-size: 13px;
  color: #888888;
}

/* 滚动条统一修饰 */
.urgent-list::-webkit-scrollbar,
.log-body::-webkit-scrollbar { 
  width: 4px; 
}
.urgent-list::-webkit-scrollbar-thumb,
.log-body::-webkit-scrollbar-thumb { 
  background: #d9d9d9; 
  border-radius: 2px; 
}
.urgent-list::-webkit-scrollbar-track,
.log-body::-webkit-scrollbar-track {
  background: transparent;
}

@media (max-width: 1200px) {
  .content-grid { grid-template-columns: 1.5fr 1fr; }
}
@media (max-width: 1024px) {
  .content-grid { grid-template-columns: 1fr; }
  .chart-card { min-height: 300px; }
  .home-page { height: auto; min-height: calc((100vh - 60px) / 0.85); }
}
</style>