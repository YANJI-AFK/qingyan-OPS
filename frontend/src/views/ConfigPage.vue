<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

const API = 'http://127.0.0.1:5000'

const config = ref({
  sla_timeout_hours: 4,
  sla_warning_pct: 75,
  ticket_desc_required: false,
  ticket_default_priority: '中',
  ticket_desc_max_chars: 500,
  dashboard_refresh_sec: 0,
  // 卡片五：通知与消息推送
  notify_new_ticket: true,
  notify_status_change: true,
  notify_overdue_method: 'all',
  notify_quiet_start: '22:00',
  notify_quiet_end: '08:00',
  // 卡片七：权限与操作门槛
  confirm_delete: true,
  confirm_assign: true,
  confirm_schedule: true,
  batch_ops_limit: 50,
  // 卡片九：数据导出配置
  export_format: 'xlsx',
  export_default_fields: 'id,title,status,priority,assignee,create_time',
  export_time_range_months: 3,
  export_max_rows: 10000,
})

const saving = ref(false)
const saveMsg = ref('')
const saveOk = ref(false)

async function loadConfig() {
  try {
    const res = await axios.get(`${API}/api/config/params`)
    const cfg = res.data
    if (cfg.sla_timeout_hours) config.value.sla_timeout_hours = Number(cfg.sla_timeout_hours)
    if (cfg.sla_warning_pct) config.value.sla_warning_pct = Number(cfg.sla_warning_pct)
    if (cfg.ticket_desc_required) config.value.ticket_desc_required = cfg.ticket_desc_required === '1'
    if (cfg.ticket_default_priority) config.value.ticket_default_priority = cfg.ticket_default_priority
    if (cfg.ticket_desc_max_chars) config.value.ticket_desc_max_chars = Number(cfg.ticket_desc_max_chars)
    if (cfg.dashboard_refresh_sec) config.value.dashboard_refresh_sec = Number(cfg.dashboard_refresh_sec)
    // 卡片五：通知
    if (cfg.notify_new_ticket !== undefined) config.value.notify_new_ticket = cfg.notify_new_ticket === '1'
    if (cfg.notify_status_change !== undefined) config.value.notify_status_change = cfg.notify_status_change === '1'
    if (cfg.notify_overdue_method) config.value.notify_overdue_method = cfg.notify_overdue_method
    if (cfg.notify_quiet_start) config.value.notify_quiet_start = cfg.notify_quiet_start
    if (cfg.notify_quiet_end) config.value.notify_quiet_end = cfg.notify_quiet_end
    // 卡片七：权限
    if (cfg.confirm_delete !== undefined) config.value.confirm_delete = cfg.confirm_delete === '1'
    if (cfg.confirm_assign !== undefined) config.value.confirm_assign = cfg.confirm_assign === '1'
    if (cfg.confirm_schedule !== undefined) config.value.confirm_schedule = cfg.confirm_schedule === '1'
    if (cfg.batch_ops_limit) config.value.batch_ops_limit = Number(cfg.batch_ops_limit)
    // 卡片九：导出
    if (cfg.export_format) config.value.export_format = cfg.export_format
    if (cfg.export_default_fields) config.value.export_default_fields = cfg.export_default_fields
    if (cfg.export_time_range_months) config.value.export_time_range_months = Number(cfg.export_time_range_months)
    if (cfg.export_max_rows) config.value.export_max_rows = Number(cfg.export_max_rows)
  } catch (e) {
    console.error('[ConfigPage] 加载配置失败:', e)
  }
}

async function saveConfig() {
  saving.value = true; saveMsg.value = ''; saveOk.value = false
  try {
    await axios.put(`${API}/api/config/params`, {
      sla_timeout_hours: String(config.value.sla_timeout_hours),
      sla_warning_pct: String(config.value.sla_warning_pct),
      ticket_desc_required: config.value.ticket_desc_required ? '1' : '0',
      ticket_default_priority: config.value.ticket_default_priority,
      ticket_desc_max_chars: String(config.value.ticket_desc_max_chars),
      dashboard_refresh_sec: String(config.value.dashboard_refresh_sec),
      // 卡片五
      notify_new_ticket: config.value.notify_new_ticket ? '1' : '0',
      notify_status_change: config.value.notify_status_change ? '1' : '0',
      notify_overdue_method: config.value.notify_overdue_method,
      notify_quiet_start: config.value.notify_quiet_start,
      notify_quiet_end: config.value.notify_quiet_end,
      // 卡片七
      confirm_delete: config.value.confirm_delete ? '1' : '0',
      confirm_assign: config.value.confirm_assign ? '1' : '0',
      confirm_schedule: config.value.confirm_schedule ? '1' : '0',
      batch_ops_limit: String(config.value.batch_ops_limit),
      // 卡片九
      export_format: config.value.export_format,
      export_default_fields: config.value.export_default_fields,
      export_time_range_months: String(config.value.export_time_range_months),
      export_max_rows: String(config.value.export_max_rows),
    })
    saveMsg.value = '配置已成功更新'; saveOk.value = true
    setTimeout(() => { saveMsg.value = '' }, 3000)
  } catch (e) {
    saveMsg.value = '保存失败，请检查网络后重试'; saveOk.value = false
  } finally { saving.value = false }
}

const refreshOptions = [
  { label: '关闭', value: 0 },
  { label: '30 秒', value: 30 },
  { label: '60 秒', value: 60 },
  { label: '120 秒', value: 120 },
  { label: '300 秒', value: 300 },
]

// 计算 SLA 预警值
const slaWarningVal = computed(() => {
  return Math.round(config.value.sla_timeout_hours * config.value.sla_warning_pct / 100 * 10) / 10
})

// 刷新状态文本
const refreshStatusText = computed(() => {
  if (config.value.dashboard_refresh_sec === 0) return '手动刷新'
  return `每 ${config.value.dashboard_refresh_sec} 秒自动刷新`
})

// 卡片五：通知方式文本
const overdueMethodLabel = computed(() => {
  const map: Record<string, string> = { mark: '看板标红', badge: '站内信', popup: '弹窗提醒', all: '全部方式' }
  return map[config.value.notify_overdue_method] || '全部方式'
})

// 通知总开关状态
const notifyEnabled = computed(() => config.value.notify_new_ticket || config.value.notify_status_change)

// 卡片七：权限复核文本
const confirmCount = computed(() => {
  let n = 0
  if (config.value.confirm_delete) n++
  if (config.value.confirm_assign) n++
  if (config.value.confirm_schedule) n++
  return n
})

// 卡片九：导出格式文本
const exportFormatLabel = computed(() => {
  const map: Record<string, string> = { csv: 'CSV', xlsx: 'Excel (.xlsx)', pdf: 'PDF' }
  return map[config.value.export_format] || 'Excel (.xlsx)'
})

// 导出字段列表
const exportFieldsList = computed(() => {
  return config.value.export_default_fields.split(',').map(s => s.trim()).filter(Boolean)
})

// 导出时间范围文本
const exportRangeLabel = computed(() => {
  if (config.value.export_time_range_months === 1) return '最近 1 个月'
  return `最近 ${config.value.export_time_range_months} 个月`
})

onMounted(loadConfig)

// 导出字段选项映射
const exportFieldOptions: Record<string, string> = {
  id: '工单号',
  title: '标题',
  status: '状态',
  priority: '优先级',
  assignee: '负责人',
  create_time: '创建时间',
  deadline: '截止时间',
  description: '描述',
  category: '分类',
}

function toggleExportField(key: string) {
  const list = exportFieldsList.value
  const idx = list.indexOf(key)
  if (idx >= 0) {
    list.splice(idx, 1)
  } else {
    list.push(key)
  }
  config.value.export_default_fields = list.join(',')
}
</script>

<template>
  <div class="config-page">
    <header class="page-header">
      <div class="header-left">
        <div class="header-icon-group">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="header-gear"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
        </div>
        <div>
          <h2 class="page-title">系统参数配置</h2>
          <p class="page-subtitle">管理 SLA 告警阈值、工单新建规则、看板刷新及通知权限导出配置</p>
        </div>
      </div>
      <div class="header-actions">
        <Transition name="fade">
          <span v-if="saveMsg" class="save-status" :class="{ 'is-success': saveOk, 'is-error': !saveOk }">
            <svg v-if="saveOk" viewBox="0 0 24 24" class="status-icon"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M20 6L9 17l-5-5"/></svg>
            <svg v-else viewBox="0 0 24 24" class="status-icon"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><line x1="12" y1="8" x2="12" y2="12" fill="none" stroke="currentColor" stroke-width="2"/><line x1="12" y1="16" x2="12.01" y2="16" fill="none" stroke="currentColor" stroke-width="2"/></svg>
            {{ saveMsg }}
          </span>
        </Transition>
        <button class="btn-primary" @click="saveConfig" :disabled="saving">
          {{ saving ? '保存中' : '保存配置' }}
          <svg v-if="saving" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
        </button>
      </div>
    </header>

    <div class="scroll-container">
      <div class="bento-grid">

        <!-- ═══ 卡片 1: SLA 告警管理 ═══ -->
        <section class="bento-card">
          <div class="card-head">
            <div class="icon-wrap" >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/><path d="M3 12h2M19 12h2M12 3V1M12 23v-2"/></svg>
            </div>
            <div class="head-text">
              <h3>SLA 告警管理</h3>
              <p>控制高优工单的超时判定标准与看板分级颜色</p>
            </div>
          </div>

          <div class="card-content">
            <!-- 参数区 -->
            <div class="param-block">
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>超时阈值</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">超过此小时数 → 看板标为红色「严重超时」</span>
                    </span>
                  </div>
                  <span class="param-value">{{ config.sla_timeout_hours }}<span class="param-unit">小时</span></span>
                </div>
                <input type="range" min="1" max="48" step="1" v-model.number="config.sla_timeout_hours" class="custom-slider" />
              </div>

              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>黄色预警</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">达到阈值的此百分比时 → 看板标为黄色「预警」</span>
                    </span>
                  </div>
                  <span class="param-value">{{ config.sla_warning_pct }}<span class="param-unit">%</span></span>
                </div>
                <input type="range" min="30" max="95" step="5" v-model.number="config.sla_warning_pct" class="custom-slider" />
              </div>
            </div>

            <!-- 预览区：SLA 时间轴 -->
            <div class="preview-block">
              <div class="preview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span>分级预览</span>
              </div>
              <div class="sla-timeline">
                <div class="sla-track">
                  <div class="sla-zone safe" :style="{ flex: slaWarningVal }">
                    <span class="zone-label" v-if="slaWarningVal > 0">安全</span>
                  </div>
                  <div class="sla-zone warning" :style="{ flex: config.sla_timeout_hours - slaWarningVal }">
                    <span class="zone-label" v-if="config.sla_timeout_hours - slaWarningVal > 0.3">预警</span>
                  </div>
                  <div class="sla-zone critical" :style="{ flex: 2 }">
                    <span class="zone-label">超时</span>
                  </div>
                </div>
                <div class="sla-marks">
                  <span class="sla-mark">0h</span>
                  <span class="sla-mark">{{ slaWarningVal }}h</span>
                  <span class="sla-mark">{{ config.sla_timeout_hours }}h</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ═══ 卡片 2: 工单新建规则 ═══ -->
        <section class="bento-card">
          <div class="card-head">
            <div class="icon-wrap" >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 5v14M5 12h14"/></svg>
            </div>
            <div class="head-text">
              <h3>工单新建规则</h3>
              <p>控制新建工单弹窗的字段约束与默认值</p>
            </div>
          </div>

          <div class="card-content">
            <!-- 参数区 -->
            <div class="param-block">
              <div class="param-row">
                <div class="param-label">
                  <span>强制填写描述</span>
                  <span class="tooltip-wrap">
                    <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                    <span class="tooltip-content">开启后新建工单时描述不允许留空</span>
                  </span>
                </div>
                <button class="ios-switch" :class="{ active: config.ticket_desc_required }" @click="config.ticket_desc_required = !config.ticket_desc_required">
                  <span class="knob"></span>
                </button>
              </div>

              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span>默认优先级</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">新建弹窗优先级的初始选中项</span>
                    </span>
                  </div>
                </div>
                <div class="priority-group">
                  <button
                    v-for="p in ['高','中','低']" :key="p"
                    class="priority-btn"
                    :class="[{ active: config.ticket_default_priority === p }, 'prio-'+p]"
                    @click="config.ticket_default_priority = p"
                  >{{ p }}</button>
                </div>
              </div>

              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span>描述字符上限</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">超出部分将被自动截断</span>
                    </span>
                  </div>
                  <span class="param-value">{{ config.ticket_desc_max_chars }}<span class="param-unit">字符</span></span>
                </div>
                <input type="range" min="100" max="2000" step="50" v-model.number="config.ticket_desc_max_chars" class="custom-slider" />
              </div>
            </div>

            <!-- 预览区：模拟新建表单 -->
            <div class="preview-block">
              <div class="preview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
                <span>新建弹窗预览</span>
              </div>
              <div class="form-preview">
                <div class="fp-field">
                  <span class="fp-label">标题</span>
                  <span class="fp-input-dummy">请输入工单标题</span>
                </div>
                <div class="fp-field">
                  <span class="fp-label">优先级</span>
                  <span class="fp-tag-group">
                    <span v-for="p in ['高','中','低']" :key="p" class="fp-tag" :class="['fp-'+p, { active: config.ticket_default_priority === p }]">{{ p }}</span>
                  </span>
                </div>
                <div class="fp-field">
                  <span class="fp-label">描述</span>
                  <span class="fp-input-dummy thin">
                    {{ config.ticket_desc_required ? '* 必填' : '选填' }}
                  </span>
                  <span class="fp-hint">≤ {{ config.ticket_desc_max_chars }} 字符</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ═══ 卡片 3: 看板自动刷新 ═══ -->
        <section class="bento-card">
          <div class="card-head">
            <div class="icon-wrap" >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </div>
            <div class="head-text">
              <h3>看板自动刷新</h3>
              <p>监控大盘与工单统计看板的数据自动拉取间隔</p>
            </div>
          </div>

          <div class="card-content">
            <!-- 刷新间隔 -->
            <div class="dc-section">
              <div class="dc-label">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span>刷新间隔</span>
              </div>
              <div class="dc-select-wrap">
                <select v-model.number="config.dashboard_refresh_sec" class="dc-select">
                  <option v-for="o in refreshOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
                <svg class="dc-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
              <div class="dc-status" :class="{ off: config.dashboard_refresh_sec === 0 }">
                <span class="dc-dot"></span>
                <span>{{ refreshStatusText }}</span>
              </div>
            </div>

            <!-- 受影响页面 -->
            <div class="dc-section">
              <div class="dc-pages">
                <div class="dc-page-item">
                  <div class="dc-page-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                  </div>
                  <div class="dc-page-text">
                    <span class="dc-page-name">监控大盘</span>
                    <span class="dc-page-desc">服务器指标实时数据</span>
                  </div>
                </div>
                <div class="dc-page-item">
                  <div class="dc-page-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
                  </div>
                  <div class="dc-page-text">
                    <span class="dc-page-name">工单统计看板</span>
                    <span class="dc-page-desc">KPI 与趋势图表</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 提示卡 -->
            <div class="dc-tip">
              <div class="dc-tip-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              </div>
              <div class="dc-tip-text">
                <strong>建议</strong>
                <p>系统负载较高或网络有限时，设为「关闭」节省资源。</p>
              </div>
            </div>
          </div>
        </section>

        <!-- ═══ 卡片五：通知与消息推送 ═══ -->
        <section class="bento-card">
          <div class="card-head">
            <div class="icon-wrap" >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            </div>
            <div class="head-text">
              <h3>通知与消息推送</h3>
              <p>控制工单流转时的消息通知方式与静默时段</p>
            </div>
          </div>

          <div class="card-content">
            <div class="param-block">
              <!-- 新工单通知 -->
              <div class="param-row">
                <div class="param-label">
                  <span>新工单通知</span>
                  <span class="tooltip-wrap">
                    <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                    <span class="tooltip-content">新建工单时给负责人发送通知</span>
                  </span>
                </div>
                <button class="ios-switch" :class="{ active: config.notify_new_ticket }" @click="config.notify_new_ticket = !config.notify_new_ticket">
                  <span class="knob"></span>
                </button>
              </div>
              <!-- 状态变更通知 -->
              <div class="param-row">
                <div class="param-label">
                  <span>状态变更通知</span>
                  <span class="tooltip-wrap">
                    <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                    <span class="tooltip-content">工单状态变化时通知相关人员</span>
                  </span>
                </div>
                <button class="ios-switch" :class="{ active: config.notify_status_change }" @click="config.notify_status_change = !config.notify_status_change">
                  <span class="knob"></span>
                </button>
              </div>
              <!-- 超时告警方式 -->
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>超时告警方式</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">选择超时工单的告警推送方式</span>
                    </span>
                  </div>
                  <span class="param-value">{{ overdueMethodLabel }}</span>
                </div>
                <div class="nt-radio-group">
                  <label class="nt-radio" :class="{ active: config.notify_overdue_method === 'mark' }">
                    <input type="radio" value="mark" v-model="config.notify_overdue_method" />
                    <span>看板标红</span>
                  </label>
                  <label class="nt-radio" :class="{ active: config.notify_overdue_method === 'badge' }">
                    <input type="radio" value="badge" v-model="config.notify_overdue_method" />
                    <span>站内信</span>
                  </label>
                  <label class="nt-radio" :class="{ active: config.notify_overdue_method === 'popup' }">
                    <input type="radio" value="popup" v-model="config.notify_overdue_method" />
                    <span>弹窗提醒</span>
                  </label>
                  <label class="nt-radio" :class="{ active: config.notify_overdue_method === 'all' }">
                    <input type="radio" value="all" v-model="config.notify_overdue_method" />
                    <span>全部方式</span>
                  </label>
                </div>
              </div>
              <!-- 静默时段 -->
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>静默时段</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">此时间段内不推送通知，避免打扰休息</span>
                    </span>
                  </div>
                </div>
                <div class="nt-time-range">
                  <div class="nt-time-field">
                    <span class="nt-time-label">开始</span>
                    <input type="time" v-model="config.notify_quiet_start" class="nt-time-input" />
                  </div>
                  <span class="nt-time-sep">至</span>
                  <div class="nt-time-field">
                    <span class="nt-time-label">结束</span>
                    <input type="time" v-model="config.notify_quiet_end" class="nt-time-input" />
                  </div>
                </div>
              </div>
            </div>

            <!-- 预览区：通知状态摘要 -->
            <div class="preview-block" v-if="notifyEnabled">
              <div class="preview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/></svg>
                <span>通知预览</span>
              </div>
              <div class="nt-preview">
                <div class="nt-preview-item" v-if="config.notify_new_ticket">
                  <span class="nt-preview-dot" ></span>
                  <span>新工单 → 负责人站内通知</span>
                </div>
                <div class="nt-preview-item" v-if="config.notify_status_change">
                  <span class="nt-preview-dot" ></span>
                  <span>状态变更 → 相关人通知</span>
                </div>
                <div class="nt-preview-item">
                  <span class="nt-preview-dot" ></span>
                  <span>超时告警 → {{ overdueMethodLabel }}</span>
                </div>
                <div class="nt-preview-item quiet">
                  <span class="nt-preview-dot" ></span>
                  <span>静默时段 {{ config.notify_quiet_start }} - {{ config.notify_quiet_end }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ═══ 卡片七：权限与操作门槛 ═══ -->
        <section class="bento-card">
          <div class="card-head">
            <div class="icon-wrap" >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            </div>
            <div class="head-text">
              <h3>权限与操作门槛</h3>
              <p>控制敏感操作是否需要二次确认，防止误操作</p>
            </div>
          </div>

          <div class="card-content">
            <div class="param-block">
              <!-- 删除需确认 -->
              <div class="param-row">
                <div class="param-label">
                  <span class="pm-label-icon" >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </span>
                  <span>删除工单需确认</span>
                  <span class="tooltip-wrap">
                    <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                    <span class="tooltip-content">语音或批量删除时需二次确认，防止误删</span>
                  </span>
                </div>
                <button class="ios-switch" :class="{ active: config.confirm_delete }" @click="config.confirm_delete = !config.confirm_delete">
                  <span class="knob"></span>
                </button>
              </div>
              <!-- 指派需确认 -->
              <div class="param-row">
                <div class="param-label">
                  <span class="pm-label-icon" >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>
                  </span>
                  <span>指派工单需确认</span>
                  <span class="tooltip-wrap">
                    <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                    <span class="tooltip-content">语音指派时需二次确认，防止派错人</span>
                  </span>
                </div>
                <button class="ios-switch" :class="{ active: config.confirm_assign }" @click="config.confirm_assign = !config.confirm_assign">
                  <span class="knob"></span>
                </button>
              </div>
              <!-- 排班需确认 -->
              <div class="param-row">
                <div class="param-label">
                  <span class="pm-label-icon" >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                  </span>
                  <span>排班修改需确认</span>
                  <span class="tooltip-wrap">
                    <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                    <span class="tooltip-content">语音排班操作时需二次确认</span>
                  </span>
                </div>
                <button class="ios-switch" :class="{ active: config.confirm_schedule }" @click="config.confirm_schedule = !config.confirm_schedule">
                  <span class="knob"></span>
                </button>
              </div>
              <!-- 批量操作上限 -->
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>批量操作上限</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">单次批量处理操作最多处理 N 条工单</span>
                    </span>
                  </div>
                  <span class="param-value">{{ config.batch_ops_limit }}<span class="param-unit">条</span></span>
                </div>
                <input type="range" min="10" max="200" step="10" v-model.number="config.batch_ops_limit" class="custom-slider" />
              </div>
            </div>

            <!-- 预览区：安全摘要 -->
            <div class="preview-block">
              <div class="preview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                <span>安全状态</span>
              </div>
              <div class="pm-summary">
                <div class="pm-summary-item" :class="{ safe: confirmCount >= 3, warn: confirmCount > 0 && confirmCount < 3, danger: confirmCount === 0 }">
                  <span class="pm-summary-icon">
                    <svg v-if="confirmCount >= 3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  </span>
                  <span>{{ confirmCount >= 3 ? '所有操作已启用二次确认，安全等级高' : confirmCount > 0 ? '部分操作已启用二次确认' : '所有操作无需二次确认，请谨慎' }}</span>
                </div>
                <div class="pm-summary-item">
                  <span class="pm-summary-icon" style="color:#0ea5e9">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                  </span>
                  <span>批量操作上限：{{ config.batch_ops_limit }} 条/次</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ═══ 卡片九：数据导出配置 ═══ -->
        <section class="bento-card">
          <div class="card-head">
            <div class="icon-wrap" >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </div>
            <div class="head-text">
              <h3>数据导出配置</h3>
              <p>控制工单数据的导出格式与默认字段</p>
            </div>
          </div>

          <div class="card-content">
            <div class="param-block">
              <!-- 导出格式 -->
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>导出格式</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">选择导出的文件格式</span>
                    </span>
                  </div>
                  <span class="param-value">{{ exportFormatLabel }}</span>
                </div>
                <div class="nt-radio-group">
                  <label class="nt-radio" :class="{ active: config.export_format === 'csv' }">
                    <input type="radio" value="csv" v-model="config.export_format" />
                    <span>CSV</span>
                  </label>
                  <label class="nt-radio" :class="{ active: config.export_format === 'xlsx' }">
                    <input type="radio" value="xlsx" v-model="config.export_format" />
                    <span>Excel (.xlsx)</span>
                  </label>
                  <label class="nt-radio" :class="{ active: config.export_format === 'pdf' }">
                    <input type="radio" value="pdf" v-model="config.export_format" />
                    <span>PDF</span>
                  </label>
                </div>
              </div>
              <!-- 默认导出字段 -->
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>默认导出字段</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">勾选导出时默认包含的字段，用逗号分隔保存</span>
                    </span>
                  </div>
                </div>
                <div class="ex-field-grid">
                  <label class="ex-field-check" v-for="(label, key) in exportFieldOptions" :key="key" :class="{ active: exportFieldsList.includes(key) }">
                    <input type="checkbox" :checked="exportFieldsList.includes(key)" @change="toggleExportField(key)" />
                    <span>{{ label }}</span>
                  </label>
                </div>
              </div>
              <!-- 时间范围 -->
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>默认时间范围</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">导出时默认选取最近 N 个月的数据</span>
                    </span>
                  </div>
                  <span class="param-value">{{ exportRangeLabel }}</span>
                </div>
                <input type="range" min="1" max="12" step="1" v-model.number="config.export_time_range_months" class="custom-slider" />
              </div>
              <!-- 最大导出数 -->
              <div class="param-item">
                <div class="param-label-row">
                  <div class="param-label">
                    <span class="param-label-dot" ></span>
                    <span>最大导出行数</span>
                    <span class="tooltip-wrap">
                      <svg class="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><text x="12" y="16" text-anchor="middle" font-size="14" font-weight="400" fill="currentColor">?</text></svg>
                      <span class="tooltip-content">单次导出最多包含的行数，超出将被截断</span>
                    </span>
                  </div>
                  <span class="param-value">{{ config.export_max_rows.toLocaleString() }}<span class="param-unit">行</span></span>
                </div>
                <input type="range" min="1000" max="50000" step="1000" v-model.number="config.export_max_rows" class="custom-slider" />
              </div>
            </div>

            <!-- 预览区：导出摘要 -->
            <div class="preview-block">
              <div class="preview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/></svg>
                <span>导出预览</span>
              </div>
              <div class="ex-preview">
                <div class="ex-preview-row">
                  <span class="ex-preview-label">格式</span>
                  <span class="ex-preview-val">{{ exportFormatLabel }}</span>
                </div>
                <div class="ex-preview-row">
                  <span class="ex-preview-label">字段</span>
                  <span class="ex-preview-val">{{ exportFieldsList.length }} 个字段</span>
                </div>
                <div class="ex-preview-row">
                  <span class="ex-preview-label">时间</span>
                  <span class="ex-preview-val">{{ exportRangeLabel }}</span>
                </div>
                <div class="ex-preview-row">
                  <span class="ex-preview-label">上限</span>
                  <span class="ex-preview-val">{{ config.export_max_rows.toLocaleString() }} 行</span>
                </div>
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════ 变量 ═══════════════════ */
.config-page {
  --c-bg: #f8fafc;
  --c-surface: #ffffff;
  --c-text: #1e293b;
  --c-text-sec: #475569;
  --c-text-muted: #94a3b8;
  --c-border: #e2e8f0;
  --c-border-light: #f1f5f9;
  --c-primary: #3b82f6;
  --c-primary-hover: #2563eb;
  --c-primary-bg: #eff6ff;
  --c-success: #10b981;
  --c-error: #ef4444;
  --c-warning: #f59e0b;

  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
  background: var(--c-bg);
  font-family: "Microsoft YaHei", "微软雅黑", -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--c-text);
}

/* 确保所有原生输入元素也继承微软雅黑 */
.config-page input,
.config-page select,
.config-page button,
.config-page textarea {
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
}

/* ═══════════════════ 顶部 ═══════════════════ */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 36px;
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
  z-index: 2;
}
.header-left { display: flex; align-items: center; gap: 14px; }
.header-icon-group {
  width: 42px; height: 42px; border-radius: 10px;
  background: #f1f5f9; display: flex;
  align-items: center; justify-content: center;
}
.header-gear { width: 22px; height: 22px; color: var(--c-text); animation: gearSpin 12s linear infinite; }
@keyframes gearSpin { to { transform: rotate(360deg); } }
.page-title { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -0.3px; }
.page-subtitle { margin: 2px 0 0; font-size: 13px; color: var(--c-text-muted); }

.header-actions { display: flex; align-items: center; gap: 16px; }
.btn-primary {
  display: flex; align-items: center; gap: 8px;
  background: #ffffff; color: #0f172a;
  border: 1px solid #cbd5e1; border-radius: 8px;
  padding: 9px 22px; font-size: 13px; font-weight: 400;
  cursor: pointer; transition: all 0.2s;
  box-shadow: none; white-space: nowrap;
}
.btn-primary:hover:not(:disabled) { border-color: #94a3b8; background: rgba(0,0,0,0.02); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.spin-icon { width: 15px; height: 15px; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.save-status { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; }
.save-status.is-success { color: var(--c-success); }
.save-status.is-error { color: var(--c-error); }
.status-icon { width: 16px; height: 16px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.25s, transform 0.25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(3px); }

/* ═══════════════════ 布局 ═══════════════════ */
.scroll-container {
  flex: 1; overflow-y: auto; padding: 28px 36px;
}
.bento-grid {
  max-width: 1200px; margin: 0 auto;
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;
  align-items: stretch;
}
.full-width { grid-column: 1 / -1; }

/* ═══════════════════ 卡片 ═══════════════════ */
.bento-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 12px;
  display: flex; flex-direction: column;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.bento-card:hover { border-color: #cbd5e1; box-shadow: 0 4px 16px rgba(0,0,0,0.04); }

.card-head {
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--c-border-light);
  display: flex; align-items: center; gap: 12px;
}
.icon-wrap {
  width: 36px; height: 36px; border-radius: 9px;
  background: var(--c-primary-bg); color: var(--c-primary);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.icon-wrap svg { width: 18px; height: 18px; }
.head-text h3 { margin: 0 0 2px; font-size: 14px; font-weight: 600; color: var(--c-text); }
.head-text p { margin: 0; font-size: 12px; color: var(--c-text-muted); line-height: 1.4; }

.card-content { padding: 16px 22px 20px; display: flex; flex-direction: column; gap: 18px; flex: 1; }

/* ═══════════════════ 参数控件 ═══════════════════ */
.param-block { display: flex; flex-direction: column; gap: 16px; }
.param-item { display: flex; flex-direction: column; gap: 6px; }
.param-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 2px 0;
}
.param-label-row { display: flex; justify-content: space-between; align-items: flex-end; }
.param-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--c-text-sec); }
.param-label-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; display: inline-block; background: #94a3b8; }
.param-value { font-size: 18px; font-weight: 600; color: var(--c-primary); font-variant-numeric: tabular-nums; line-height: 1; }
.param-unit { font-size: 12px; font-weight: 400; color: var(--c-text-muted); margin-left: 3px; }

/* tooltip */
.tooltip-wrap { position: relative; display: inline-flex; align-items: center; cursor: help; }
.info-icon { width: 14px; height: 14px; color: #cbd5e1; transition: color 0.15s; }
.tooltip-wrap:hover .info-icon { color: var(--c-text-sec); }
.tooltip-content {
  position: absolute; bottom: 150%; left: 50%;
  transform: translateX(-50%) translateY(6px);
  background: #1e293b;
  color: #f1f5f9; padding: 8px 12px; border-radius: 6px;
  font-size: 12px; line-height: 1.5; white-space: nowrap;
  opacity: 0; visibility: hidden;
  transition: all 0.18s ease; pointer-events: none;
  z-index: 10; text-align: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
.tooltip-content::after {
  content: ''; position: absolute; top: 100%; left: 50%;
  margin-left: -4px; border: 4px solid transparent;
  border-top-color: #1e293b;
}
.tooltip-wrap:hover .tooltip-content { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }

/* slider */
.custom-slider {
  width: 100%; height: 5px; background: #f1f5f9;
  border-radius: 3px; outline: none; -webkit-appearance: none; cursor: pointer;
}
.custom-slider::-webkit-slider-thumb {
  -webkit-appearance: none; width: 18px; height: 18px; background: #fff;
  border: 2px solid var(--c-primary); border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); transition: transform 0.12s;
  cursor: grab;
}
.custom-slider::-webkit-slider-thumb:hover { transform: scale(1.12); }

/* ios switch */
.ios-switch {
  position: relative; width: 44px; height: 24px; border-radius: 12px;
  background: #d1d5db; border: none; cursor: pointer; flex-shrink: 0;
  transition: background 0.25s; padding: 0; outline: none;
}
.ios-switch.active { background: #3b82f6; }
.ios-switch .knob {
  position: absolute; top: 2px; left: 2px; width: 20px; height: 20px;
  background: #fff; border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
  transition: transform 0.25s cubic-bezier(0.4,0,0.2,1);
}
.ios-switch.active .knob { transform: translateX(20px); }

/* priority group */
.priority-group {
  display: flex; gap: 6px; background: #f1f5f9;
  padding: 3px; border-radius: 8px;
}
.priority-btn {
  flex: 1; padding: 7px 0; border: none; border-radius: 5px;
  background: transparent; font-size: 13px; font-weight: 500;
  color: var(--c-text-muted); cursor: pointer;
  transition: all 0.18s;
}
.priority-btn:hover:not(.active) { color: var(--c-text); }
.priority-btn.active { color: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.priority-btn.active.prio-高 { background: #ef4444; }
.priority-btn.active.prio-中 { background: #f59e0b; }
.priority-btn.active.prio-低 { background: #10b981; }

/* ═══════════════════ 预览区块 ═══════════════════ */
.preview-block {
  background: #f8fafc; border: 1px solid var(--c-border-light);
  border-radius: 10px; padding: 14px 16px; margin-top: auto;
}
.preview-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 600; color: var(--c-text-muted);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;
}
.preview-title svg { width: 13px; height: 13px; }

/* SLA 时间轴 */
.sla-timeline { display: flex; flex-direction: column; gap: 6px; }
.sla-track { display: flex; height: 28px; border-radius: 6px; overflow: hidden; }
.sla-zone { display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; transition: flex 0.3s; }
.sla-zone.safe { background: #d1fae5; color: #065f46; }
.sla-zone.warning { background: #fef3c7; color: #92400e; }
.sla-zone.critical { background: #fee2e2; color: #991b1b; }
.zone-label { white-space: nowrap; }
.sla-marks { display: flex; justify-content: space-between; font-size: 11px; color: var(--c-text-muted); padding: 0 2px; }

/* 表单预览 */
.form-preview { display: flex; flex-direction: column; gap: 8px; }
.fp-field { display: flex; align-items: center; gap: 10px; }
.fp-label { width: 50px; font-size: 12px; font-weight: 500; color: var(--c-text-muted); flex-shrink: 0; }
.fp-input-dummy {
  flex: 1; padding: 6px 10px; background: #fff; border: 1px solid #e2e8f0;
  border-radius: 5px; font-size: 12px; color: #94a3b8;
}
.fp-input-dummy.thin { padding: 5px 10px; }
.fp-hint { font-size: 11px; color: var(--c-text-muted); white-space: nowrap; }
.fp-tag-group { display: flex; gap: 4px; }
.fp-tag {
  padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 500;
  color: var(--c-text-muted); background: #f1f5f9; transition: all 0.15s;
}
.fp-tag.active { color: #fff; }
.fp-tag.fp-高.active { background: #ef4444; }
.fp-tag.fp-中.active { background: #f59e0b; }
.fp-tag.fp-低.active { background: #10b981; }

/* ═══════════════════ 看板刷新卡片 ═══════════════════ */
.dc-section { display: flex; flex-direction: column; gap: 10px; }
.dc-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 500; color: var(--c-text-sec);
}
.dc-label svg { width: 15px; height: 15px; color: var(--c-text-muted); }
.dc-select-wrap { position: relative; }
.dc-select {
  width: 100%; padding: 10px 14px; padding-right: 36px;
  font-size: 14px; color: var(--c-text); font-weight: 500;
  background: #f8fafc; border: 1px solid var(--c-border);
  border-radius: 8px; appearance: none; cursor: pointer; outline: none;
  transition: border-color 0.15s, background 0.15s;
}
.dc-select:hover, .dc-select:focus { border-color: #94a3b8; background: #fff; }
.dc-arrow {
  position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
  width: 16px; height: 16px; color: var(--c-text-muted); pointer-events: none;
}
.dc-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 500; color: var(--c-success);
}
.dc-status.off { color: var(--c-text-muted); }
.dc-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: currentColor; flex-shrink: 0;
}
.dc-status.off .dc-dot { background: var(--c-text-muted); }

.dc-pages { display: flex; flex-direction: column; gap: 8px; }
.dc-page-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; background: #f8fafc;
  border: 1px solid #f1f5f9; border-radius: 8px;
}
.dc-page-icon {
  width: 34px; height: 34px; border-radius: 8px;
  background: var(--c-primary-bg); color: var(--c-primary);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.dc-page-icon svg { width: 17px; height: 17px; }
.dc-page-text { display: flex; flex-direction: column; gap: 2px; }
.dc-page-name { font-size: 13px; font-weight: 600; color: var(--c-text); }
.dc-page-desc { font-size: 11px; color: var(--c-text-muted); }

.dc-tip {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px; background: #f8fafc;
  border: 1px solid var(--c-border-light); border-radius: 10px;
}
.dc-tip-icon {
  width: 28px; height: 28px; border-radius: 7px;
  background: var(--c-primary-bg); color: var(--c-primary);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.dc-tip-icon svg { width: 16px; height: 16px; }
.dc-tip-text { display: flex; flex-direction: column; gap: 4px; }
.dc-tip-text strong { font-size: 13px; color: var(--c-text); }
.dc-tip-text p { margin: 0; font-size: 12px; color: var(--c-text-sec); line-height: 1.5; }

/* ═══════════════════ 卡片五：通知 ═══════════════════ */
.nt-radio-group {
  display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px;
}
.nt-radio {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 6px;
  border: 1px solid var(--c-border);
  background: #fafbfc; cursor: pointer;
  transition: all 0.15s; font-size: 12px; color: var(--c-text-sec);
}
.nt-radio input { display: none; }
.nt-radio.active {
  border-color: var(--c-primary); background: var(--c-primary-bg); color: var(--c-primary);
}
.nt-time-range {
  display: flex; align-items: center; gap: 10px; margin-top: 10px;
}
.nt-time-field { display: flex; align-items: center; gap: 6px; }
.nt-time-label { font-size: 12px; color: var(--c-text-muted); white-space: nowrap; }
.nt-time-input {
  padding: 5px 10px; border: 1px solid var(--c-border); border-radius: 6px;
  font-size: 13px; color: var(--c-text); background: #fafbfc; outline: none;
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
}
.nt-time-input:focus { border-color: var(--c-primary); }
.nt-time-sep { font-size: 12px; color: var(--c-text-muted); }
.nt-preview {
  display: flex; flex-direction: column; gap: 6px; padding: 2px 0;
}
.nt-preview-item {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--c-text-sec); line-height: 1.5;
}
.nt-preview-item.quiet { opacity: 0.7; }
.nt-preview-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: #94a3b8;
}

/* ═══════════════════ 卡片七：权限 ═══════════════════ */
.pm-label-icon {
  width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; color: var(--c-text-muted);
}
.pm-label-icon svg { width: 16px; height: 16px; }
.pm-summary {
  display: flex; flex-direction: column; gap: 8px; padding: 2px 0;
}
.pm-summary-item {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--c-text-sec); line-height: 1.5;
}
.pm-summary-item.safe { color: #16a34a; }
.pm-summary-item.warn { color: #d97706; }
.pm-summary-item.danger { color: #dc2626; }
.pm-summary-icon {
  width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.pm-summary-icon svg { width: 16px; height: 16px; }

/* ═══════════════════ 卡片九：导出 ═══════════════════ */
.ex-field-grid {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px;
}
.ex-field-check {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 6px;
  border: 1px solid var(--c-border);
  background: #fafbfc; cursor: pointer;
  transition: all 0.15s; font-size: 12px; color: var(--c-text-sec);
}
.ex-field-check input { display: none; }
.ex-field-check.active {
  border-color: var(--c-primary); background: var(--c-primary-bg); color: var(--c-primary);
}
.ex-preview {
  display: flex; flex-direction: column; gap: 6px; padding: 2px 0;
}
.ex-preview-row {
  display: flex; align-items: center; gap: 12px; font-size: 12px; line-height: 1.6;
}
.ex-preview-label {
  width: 44px; flex-shrink: 0; color: var(--c-text-muted);
}
.ex-preview-val {
  color: var(--c-text-sec);
}

/* ═══════════════════ 响应式 ═══════════════════ */
@media (max-width: 1100px) {
  .bento-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 768px) {
  .bento-grid { grid-template-columns: 1fr; }
  .page-header { padding: 16px 20px; }
  .scroll-container { padding: 20px; }
}
</style>
