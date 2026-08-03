<script setup lang="ts">
/**
 * StatsPage.vue — 工单统计看板 (极简 Bento 布局版 - 优化重构版)
 */
import { ref, onMounted, onUnmounted, nextTick, computed, watch } from 'vue'
import * as echarts from 'echarts'
import axios from 'axios'

const API = 'http://127.0.0.1:5000'

// ========== 时间筛选 ==========
type RangeKey = 'today' | '7d' | '14d' | '30d'
const rangeOptions: { key: RangeKey; label: string; days: number }[] = [
  { key: 'today', label: '今日', days: 1 },
  { key: '7d', label: '近7天', days: 7 },
  { key: '14d', label: '近14天', days: 14 },
  { key: '30d', label: '近30天', days: 30 },
]
const activeRange = ref<RangeKey>('7d')

// ========== 数据状态 ==========
const loading = ref(true)
const errorMsg = ref('')
const statsUpdateTime = ref('')
const lastRefreshText = ref('')
const autoRefresh = ref(true)
const refreshIntervalSec = ref(30)  // 默认30秒，启动时从配置读取
let refreshTimer: ReturnType<typeof setInterval> | null = null

const kpi = ref({
  total_count: 0, today_new: 0, completed_count: 0, in_progress_count: 0,
  pending_count: 0, completion_rate: 0, avg_response_hours: 0, sla_overdue: 0,
})
const trendData = ref<{ date: string; new: number; closed: number }[]>([])
const priorityDist = ref<Record<string, number>>({})
const statusDist = ref<Record<string, number>>({})
const efficiencyRank = ref<{ assignee: string; done_count: number; rank: number }[]>([])
const avgDuration = ref<Record<string, number>>({})
const slaWarningList = ref<{ id: string; title: string; priority: string; assignee: string; overdue_hours: number }[]>([])
const recentTickets = ref<any[]>([])
const meta = ref({ days: 7, sla_hours: 4 })

const currentDaysLabel = computed(() => rangeOptions.find(r => r.key === activeRange.value)?.label || '近7天')

// ========== ECharts 实例管理 ==========
const trendRef = ref<HTMLDivElement | null>(null)
const pieRef = ref<HTMLDivElement | null>(null)

let chartInstances: Record<string, echarts.ECharts | null> = { trend: null, pie: null }
let resizeHandler: (() => void) | null = null

// ========== 数据加载 ==========
async function loadData() {
  loading.value = true
  errorMsg.value = ''
  try {
    const days = rangeOptions.find(r => r.key === activeRange.value)?.days ?? 7
    const res = await axios.get(`${API}/api/stats/dashboard`, { params: { days } })
    if (res.data.error) { errorMsg.value = res.data.error; return }

    const d = res.data
    kpi.value = d.kpi || kpi.value
    trendData.value = d.trend_data || []
    priorityDist.value = d.priority_distribution || {}
    statusDist.value = d.status_distribution || {}
    efficiencyRank.value = d.efficiency_rank || []
    avgDuration.value = d.avg_duration || {}
    slaWarningList.value = d.sla_warning_list || []
    recentTickets.value = d.recent_tickets || []
    meta.value = d._meta || meta.value

    statsUpdateTime.value = new Date().toLocaleTimeString('zh-CN')

    await nextTick()
    renderAllCharts()
  } catch (e: any) {
    errorMsg.value = '数据加载失败，请检查网络或后端服务'
  } finally {
    loading.value = false
  }
}

// ========== 图表渲染 ==========
function disposeAll() {
  Object.keys(chartInstances).forEach(k => {
    try { chartInstances[k]?.dispose() } catch { /* ignore */ }
    chartInstances[k] = null
  })
}

function getOrInitChart(refEl: HTMLElement | null, key: string): echarts.ECharts {
  if (!refEl) throw new Error(`ref ${key} is null`)
  if (chartInstances[key] && !chartInstances[key]!.isDisposed()) return chartInstances[key]!
  chartInstances[key] = echarts.init(refEl)
  return chartInstances[key]!
}

function renderAllCharts() {
  if (!trendRef.value) return
  renderTrendChart()
  renderPriorityPie()
}

// 1. 工单趋势 - 极简曲线
function renderTrendChart() {
  const chart = getOrInitChart(trendRef.value, 'trend')
  const dates = trendData.value.map(d => d.date.slice(5))
  const hasData = dates.length > 0
  
  chart.setOption({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255,255,255,0.95)', extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 8px;' },
    legend: { data: ['新增', '关闭'], top: 0, right: 0, icon: 'circle', itemWidth: 8, textStyle: { color: '#64748b' } },
    grid: { left: 0, right: 10, top: 40, bottom: 0, containLabel: true },
    xAxis: { 
      type: 'category', data: hasData ? dates : ['暂无'], 
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#94a3b8', margin: 12 }
    },
    yAxis: { 
      type: 'value', minInterval: 1, 
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } }, 
      axisLabel: { color: '#94a3b8' } 
    },
    series: [
      {
        name: '新增', type: 'line', data: hasData ? trendData.value.map(d => d.new) : [],
        smooth: true, showSymbol: false, lineStyle: { width: 3, color: '#3b82f6' }, itemStyle: { color: '#3b82f6' }
      },
      {
        name: '关闭', type: 'line', data: hasData ? trendData.value.map(d => d.closed) : [],
        smooth: true, showSymbol: false, lineStyle: { width: 3, color: '#10b981' }, itemStyle: { color: '#10b981' }
      }
    ]
  }, { notMerge: true })
}

// 2. 优先级分布 - 展示丰富标签的环形图
function renderPriorityPie() {
  const chart = getOrInitChart(pieRef.value, 'pie')
  const pData = [
    { value: priorityDist.value['高'] || 0, name: '高' },
    { value: priorityDist.value['中'] || 0, name: '中' },
    { value: priorityDist.value['低'] || 0, name: '低' },
  ].filter(d => d.value > 0)
  
  const hasData = pData.length > 0
  const total = pData.reduce((s, d) => s + d.value, 0)

  chart.setOption({
    tooltip: { trigger: 'item', backgroundColor: 'rgba(255,255,255,0.95)', formatter: '{b}优先级: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { color: '#64748b' } },
    series: [{
      type: 'pie', 
      radius: ['45%', '65%'], /* 缩小半径，为外部引导线和文字留出空间 */
      center: ['50%', '42%'],
      avoidLabelOverlap: true, 
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { 
        show: true, 
        formatter: '{b}\n{c} 单', 
        color: '#64748b',
        lineHeight: 18,
        fontSize: 12
      },
      labelLine: {
        show: true,
        length: 12,
        length2: 15,
        lineStyle: { color: '#cbd5e1' }
      },
      data: hasData ? pData : [{ value: 1, name: '暂无', itemStyle: { color: '#f1f5f9' }, label: { show: false } }],
      color: ['#ef4444', '#f59e0b', '#10b981'],
    }],
    graphic: hasData ? [{
      type: 'text', left: 'center', top: '38%',
      style: { text: total.toString(), textAlign: 'center', fill: '#1e293b', fontSize: 24, fontWeight: 'bold' }
    }] : []
  }, { notMerge: true })
}

// ========== 控制逻辑 ==========
function switchRange(key: RangeKey) {
  if (activeRange.value === key) return
  activeRange.value = key
  loadData()
}

function toggleAuto() {
  autoRefresh.value = !autoRefresh.value
  autoRefresh.value ? startAutoRefresh() : stopAutoRefresh()
}
function startAutoRefresh() {
  stopAutoRefresh()
  const intervalMs = refreshIntervalSec.value * 1000
  if (intervalMs <= 0) return
  refreshTimer = setInterval(() => {
    loadData()
    lastRefreshText.value = new Date().toLocaleTimeString('zh-CN')
  }, intervalMs)
}
function stopAutoRefresh() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}

function getStatusClass(s: string) { return { '已完成': 'done', '进行中': 'prog', '未完成': 'pend' }[s] || 'pend' }
function getPriorityClass(p: string) { return { '高': 'high', '中': 'mid', '低': 'low' }[p] || 'low' }

onMounted(async () => {
  // 读取配置中的看板刷新间隔
  try {
    const res = await axios.get(`${API}/api/config/params`)
    const sec = Number(res.data?.dashboard_refresh_sec) || 0
    if (sec > 0) {
      refreshIntervalSec.value = sec
    } else {
      autoRefresh.value = false  // 配置为"关闭"，则不自动刷新
    }
  } catch { /* 配置不可用，使用默认值 */ }

  loadData()
  if (autoRefresh.value) startAutoRefresh()
  resizeHandler = () => Object.values(chartInstances).forEach(c => c?.resize())
  window.addEventListener('resize', resizeHandler)
})
onUnmounted(() => {
  disposeAll()
  stopAutoRefresh()
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
})
watch([trendData, priorityDist], () => { nextTick(() => renderAllCharts()) }, { deep: true })
</script>

<template>
  <div class="dashboard-wrapper">
    <!-- 顶部操作栏 -->
    <header class="d-header">
      <div class="h-title-area">
        <h1>工单数据看板</h1>
        <span class="update-info">实时数据 · {{ currentDaysLabel }} <template v-if="statsUpdateTime">· 更新于 {{ statsUpdateTime }}</template></span>
      </div>
      
      <div class="h-actions">
        <div class="time-tabs">
          <button v-for="opt in rangeOptions" :key="opt.key" 
                  :class="['tab-btn', { active: activeRange === opt.key }]" 
                  @click="switchRange(opt.key)">
            {{ opt.label }}
          </button>
        </div>
        
        <div class="tools">
          <label class="auto-refresh-switch">
            <input type="checkbox" :checked="autoRefresh" @change="toggleAuto">
            <span class="slider"></span>
            自动刷新
          </label>
          <button class="btn-refresh" @click="loadData" :disabled="loading">
            <svg :class="{'spin': loading}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 11-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
            刷新
          </button>
        </div>
      </div>
    </header>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <!-- 1. KPI 指标 (再设计：纯净白底、线性小图标、消除颜色杂乱) -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">工单总量</span>
          <svg class="kpi-icon-min" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
        </div>
        <div class="kpi-val">{{ kpi.total_count }}</div>
      </div>
      
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">今日新增</span>
          <svg class="kpi-icon-min" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
        </div>
        <div class="kpi-val">{{ kpi.today_new }}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">已完成</span>
          <svg class="kpi-icon-min" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        </div>
        <div class="kpi-val">{{ kpi.completed_count }}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">处理中</span>
          <svg class="kpi-icon-min" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        </div>
        <div class="kpi-val">{{ kpi.in_progress_count }}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">待处理</span>
          <svg class="kpi-icon-min" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        </div>
        <div class="kpi-val">{{ kpi.pending_count }}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">完成率</span>
          <svg class="kpi-icon-min" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
        </div>
        <div class="kpi-val">{{ kpi.completion_rate }}<span class="kpi-unit">%</span></div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">平均响应</span>
          <svg class="kpi-icon-min" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        </div>
        <div class="kpi-val">{{ kpi.avg_response_hours }}<span class="kpi-unit">h</span></div>
      </div>
    </div>

    <!-- 2. Bento 网格图表区域 -->
    <div class="bento-grid">
      <!-- 趋势图 (宽) -->
      <div class="panel span-8">
        <h3 class="panel-title">工单趋势</h3>
        <div ref="trendRef" class="echart-box"></div>
      </div>
      <!-- 优先级 (窄) -->
      <div class="panel span-4">
        <h3 class="panel-title">优先级分布</h3>
        <div ref="pieRef" class="echart-box"></div>
      </div>
      <!-- SLA 面板 -->
      <div class="panel span-5 table-panel sla-panel">
        <div class="panel-header">
          <h3 class="panel-title t-red">SLA 超时预警</h3>
          <span class="badge red">{{ slaWarningList.length }}</span>
        </div>
        <div
          class="scroll-area"
          :class="{ 'is-overflow': slaWarningList.length > 5 }"
        >
          <div v-if="!slaWarningList.length" class="empty-state">状态良好，无超时</div>
          <div v-else>
            <div class="list-wrap">
              <div v-for="item in slaWarningList" :key="item.id" class="list-item">
                <div class="item-main">
                  <span class="item-id">{{ item.id }}</span>
                  <span class="item-title">{{ item.title }}</span>
                </div>
                <div class="item-sub">
                  <span class="item-user">{{ item.assignee }}</span>
                  <span class="item-tag tag-red">{{ item.overdue_hours }}h</span>
                </div>
              </div>
            </div>
            <!-- 复制一份用于无缝循环滚动 -->
            <div v-if="slaWarningList.length > 5" class="list-wrap" aria-hidden="true">
              <div v-for="item in slaWarningList" :key="'cp-' + item.id" class="list-item">
                <div class="item-main">
                  <span class="item-id">{{ item.id }}</span>
                  <span class="item-title">{{ item.title }}</span>
                </div>
                <div class="item-sub">
                  <span class="item-user">{{ item.assignee }}</span>
                  <span class="item-tag tag-red">{{ item.overdue_hours }}h</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 最近工单 -->
      <div class="panel span-7 table-panel">
        <div class="panel-header">
          <h3 class="panel-title">最近活动工单</h3>
        </div>
        <div
          class="scroll-area"
          :class="{ 'is-overflow': recentTickets.length > 5 }"
        >
          <div v-if="!recentTickets.length" class="empty-state">暂无工单数据</div>
          <table v-else class="data-table">
            <thead>
              <tr>
                <th width="15%">编号</th>
                <th width="40%">标题</th>
                <th width="15%">优先级</th>
                <th width="15%">状态</th>
                <th width="15%">负责人</th>
              </tr>
            </thead>
            <tbody class="scroll-tbody">
              <tr v-for="t in recentTickets" :key="t.id">
                <td class="t-id">{{ t.id }}</td>
                <td class="t-title"><div class="truncate" :title="t.title">{{ t.title }}</div></td>
                <td><span :class="['tag', getPriorityClass(t.priority)]">{{ t.priority }}</span></td>
                <td><span :class="['status-dot', getStatusClass(t.status)]"></span>{{ t.status }}</td>
                <td class="t-user">{{ t.assignee }}</td>
              </tr>
              <!-- 复制一份用于无缝循环滚动 -->
              <template v-if="recentTickets.length > 5">
                <tr v-for="t in recentTickets" :key="'cp-' + t.id" aria-hidden="true">
                  <td class="t-id">{{ t.id }}</td>
                  <td class="t-title"><div class="truncate" :title="t.title">{{ t.title }}</div></td>
                  <td><span :class="['tag', getPriorityClass(t.priority)]">{{ t.priority }}</span></td>
                  <td><span :class="['status-dot', getStatusClass(t.status)]"></span>{{ t.status }}</td>
                  <td class="t-user">{{ t.assignee }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 加载遮罩 -->
    <div v-if="loading" class="loader-mask">
      <div class="spinner"></div>
    </div>
  </div>
</template>

<style scoped>
/* ================= 全局变量 & 基础设定 ================= */
.dashboard-wrapper { height: calc((100vh - 60px) / 0.85); display: flex; flex-direction: column; overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #1e293b;
  background-color: transparent;
  min-height: 100%;
  position: relative;
}

/* ================= 头部区域 ================= */
.d-header {
  display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 20px; flex-wrap: wrap; gap: 16px;
}
.d-header h1 { margin: 0 0 4px 0; font-size: 24px; font-weight: 700; color: #0f172a; letter-spacing: -0.5px; }
.update-info { font-size: 13px; color: #64748b; }

.h-actions { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }

.time-tabs { display: flex; background: #f1f5f9; padding: 4px; border-radius: 8px; }
.tab-btn { 
  border: none; background: transparent; padding: 6px 16px; font-size: 13px; font-weight: 500; 
  color: #64748b; border-radius: 6px; cursor: pointer; transition: all 0.2s;
}
.tab-btn:hover { color: #0f172a; }
.tab-btn.active { background: #fff; color: #0f172a; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }

.tools { display: flex; align-items: center; gap: 16px; }
.auto-refresh-switch { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #64748b; cursor: pointer; user-select: none; }
.auto-refresh-switch input { margin: 0; cursor: pointer; accent-color: #3b82f6; width: 14px; height: 14px;}

.btn-refresh { 
  display: flex; align-items: center; gap: 6px; background: #fff; border: 1px solid #e2e8f0; 
  padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 500; color: #334155; cursor: pointer; transition: 0.2s;
}
.btn-refresh:hover { border-color: #cbd5e1; background: #f8fafc; }
.btn-refresh svg { width: 14px; height: 14px; color: #64748b; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

.error-banner { background: #fef2f2; border: 1px solid #fecaca; color: #dc2626; padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }

/* ================= 1. KPI 区域 (全新极简样式) ================= */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 16px; margin-bottom: 16px; }
.kpi-card { 
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 20px;
  display: flex; flex-direction: column; gap: 8px; transition: box-shadow 0.2s, border-color 0.2s;
}
.kpi-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.04); border-color: #cbd5e1; }
.kpi-top { display: flex; justify-content: space-between; align-items: center; }
.kpi-label { font-size: 13px; color: #64748b; font-weight: 500; }
.kpi-icon-min { width: 18px; height: 18px; color: #cbd5e1; }
.kpi-val { font-size: 26px; font-weight: 700; color: #0f172a; line-height: 1.1; }
.kpi-unit { font-size: 14px; font-weight: 500; color: #94a3b8; margin-left: 4px; }

/* ================= 2. Bento 网格区域 ================= */
.bento-grid {
  display: grid; grid-template-columns: repeat(12, 1fr); grid-template-rows: minmax(220px, 1fr) minmax(260px, 1fr);
  gap: 16px; flex: 1; min-height: 0;
}
.span-4 { grid-column: span 4; }
.span-5 { grid-column: span 5; }
.span-7 { grid-column: span 7; }
.span-8 { grid-column: span 8; }

.panel {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 20px;
  display: flex; flex-direction: column; min-height: 0; overflow: hidden;
}
.panel-title { margin: 0 0 12px 0; font-size: 14px; font-weight: 600; color: #1e293b; }
.panel-title.t-red { color: #dc2626; }
.echart-box { flex: 1; min-height: 200px; width: 100%; }

/* ================= 3. 底部列表区域 ================= */
.table-panel { padding: 0; overflow: hidden; flex: 1; min-height: 0; }
.panel-header { padding: 16px 20px 12px; border-bottom: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center; }
.badge.red { background: #fef2f2; color: #dc2626; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 10px; }

/* 自定义优雅细长滚动条 */
.scroll-area { flex: 1; overflow-y: auto; overflow-x: hidden; min-height: 0; }
.scroll-area::-webkit-scrollbar { width: 6px; }
.scroll-area::-webkit-scrollbar-track { background: transparent; }
.scroll-area::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
.scroll-area::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

/* 减慢滚动速度：18s/22s -> 40s/50s */
.scroll-area.is-overflow { overflow: hidden; }
.scroll-area.is-overflow:hover { overflow-y: auto; }
.scroll-area.is-overflow .list-wrap { animation: listScroll 40s linear infinite; }
.scroll-area.is-overflow:hover .list-wrap { animation-play-state: paused; }
.scroll-area.is-overflow .data-table { animation: tableScroll 50s linear infinite; }
.scroll-area.is-overflow:hover .data-table { animation-play-state: paused; }
@keyframes listScroll {
  0%   { transform: translateY(0); }
  100% { transform: translateY(-50%); }
}
@keyframes tableScroll {
  0%   { transform: translateY(0); }
  100% { transform: translateY(-50%); }
}

.empty-state { text-align: center; color: #94a3b8; font-size: 13px; padding: 40px 0; }

/* SLA 列表 — 统一使用微软雅黑 */
.sla-panel .list-item { 
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
}
.sla-panel .item-id { 
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; 
}
.sla-panel .item-title { 
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; 
}
.sla-panel .item-user { 
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; 
}
.sla-panel .item-tag { 
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; 
}

/* SLA 列表 */
.list-item { 
  display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; 
  border-bottom: 1px solid #f8fafc; transition: background 0.2s;
}
.list-item:hover { background: #f8fafc; }
.item-main { display: flex; flex-direction: column; gap: 4px; overflow: hidden; }
.item-id { font-size: 12px; color: #0f172a; font-family: 'Times New Roman', Times, serif; }
.item-title { font-size: 13px; color: #1e293b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500;}
.item-sub { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.item-user { font-size: 12px; color: #64748b; }
.item-tag { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.tag-red { background: #fef2f2; color: #ef4444; }

/* 数据表格 */
.data-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.data-table th { text-align: left; font-size: 12px; font-weight: 500; color: #64748b; padding: 10px 20px; background: #fafafa; border-bottom: 1px solid #f1f5f9; position: sticky; top: 0; z-index: 1;}
.data-table td { font-size: 13px; color: #334155; padding: 12px 20px; border-bottom: 1px solid #f8fafc; }
.data-table tbody tr:hover { background: #f8fafc; }
.t-id { font-family: 'Times New Roman', Times, serif; color: #0f172a; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.t-user { color: #64748b; }

/* 标签 & 状态点 */
.tag { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.tag.high { color: #ef4444; background: #fef2f2; }
.tag.mid { color: #f59e0b; background: #fffbeb; }
.tag.low { color: #10b981; background: #f0fdf4; }

.status-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px; }
.status-dot.done { background: #10b981; }
.status-dot.prog { background: #3b82f6; }
.status-dot.pend { background: #f59e0b; }

/* ================= 遮罩层 ================= */
.loader-mask { 
  position: absolute; inset: 0; background: rgba(255,255,255,0.7); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center; border-radius: 12px; z-index: 99;
}
.spinner { 
  width: 32px; height: 32px; border: 3px solid #e2e8f0; border-top-color: #3b82f6; 
  border-radius: 50%; animation: spin 0.8s linear infinite; 
}

/* ================= 响应式调整 ================= */
@media (max-width: 1280px) {
  .span-4 { grid-column: span 6; }
  .span-5 { grid-column: span 6; }
  .span-7 { grid-column: span 6; }
  .span-8 { grid-column: span 6; }
  .kpi-grid { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 900px) {
  .span-4, .span-5, .span-7, .span-8 { grid-column: span 12; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .d-header { flex-direction: column; align-items: flex-start; }
}
</style>