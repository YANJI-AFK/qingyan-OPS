<script setup lang="ts">
/**
 * SchedulePage.vue — 值班排班管理
 * - 3 KPI + 月历日历 + 月份切换 + 快速排班 + 批量排班
 * - 点击有排班的日期格 → 弹出当日排班详情
 * - 点击空日期格 → 自动填充快速排班日期
 * - 点击已排班人员标签 → 快速切换 / 删除
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const API = 'http://127.0.0.1:5000'

// ========== 视图日期 ==========
const today = new Date()
const viewYear = ref(today.getFullYear())
const viewMonth = ref(today.getMonth() + 1)

// ========== 数据 ==========
const loading = ref(true)
const kpi = ref({ today_on_duty: 0, online_count: 0, month_total_shifts: 0 })
const scheduleList = ref<{ staff_name: string; shift_date: string; shift_type: string }[]>([])
const allStaff = ref<string[]>([])
const loadData = ref<{ staff_name: string; duty_days: number }[]>([])

// ========== 快速排班 ==========
const quickForm = ref({
  staff_name: '' as string,
  shift_date: '' as string,
  shift_type: '早班' as string,
})
const quickMsg = ref('')
const quickErr = ref(false)
const shiftOptions = ['早班', '下午班', '晚班', '休息'] as const
const shiftInfoMap: Record<string, { label: string; time: string; colorVar: string; softVar: string; cssClass: string }> = {
  '早班': { label: '早班', time: '08:30-11:30', colorVar: '--morning', softVar: '--morning-soft', cssClass: 'morning' },
  '下午班': { label: '下午班', time: '14:00-18:00', colorVar: '--afternoon', softVar: '--afternoon-soft', cssClass: 'afternoon' },
  '晚班': { label: '晚班', time: '20:00-22:00', colorVar: '--evening', softVar: '--evening-soft', cssClass: 'evening' },
  '休息': { label: '休息', time: '', colorVar: '--off', softVar: '--off-soft', cssClass: 'off' },
}
const dutyShiftTypes = ['早班', '下午班', '晚班']  // 上班班次（排除休息）

// ========== 批量排班 ==========
const batchForm = ref({
  weekdays: [] as number[],
  staff_names: [] as string[],
  shift_type: '早班' as string,
  start_date: '' as string,
  end_date: '' as string,
})
const batchMsg = ref('')
const batchErr = ref(false)
const showBatch = ref(false)
const weekdayLabels = ['一', '二', '三', '四', '五', '六', '日']

// ========== 日期详情弹窗 ==========
const dayDetail = ref<{
  date: string
  dayOfWeek: string
  shifts: { staff_name: string; shift_type: string }[]
} | null>(null)

function showDayDetail(cell: { date: string; shifts: { staff_name: string; shift_type: string }[] }) {
  if (!cell.date) return
  const d = new Date(cell.date + 'T00:00:00')
  const weekNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  dayDetail.value = {
    date: cell.date,
    dayOfWeek: weekNames[d.getDay()],
    shifts: [...cell.shifts],
  }
}

function closeDayDetail() {
  dayDetail.value = null
}

// ========== 加载 ==========
async function fetchData() {
  loading.value = true
  try {
    const res = await axios.get(`${API}/api/staff/schedule`, {
      params: { year: viewYear.value, month: viewMonth.value },
    })
    kpi.value = res.data.kpi
    scheduleList.value = res.data.schedule || []
    allStaff.value = res.data.all_staff || []
    loadData.value = res.data.load_data || []

    if (allStaff.value.length && !quickForm.value.staff_name) {
      quickForm.value.staff_name = allStaff.value[0]
    }
    if (!quickForm.value.shift_date) {
      quickForm.value.shift_date = formatYMD(today)
    }
    if (!batchForm.value.start_date) {
      batchForm.value.start_date = formatYMD(today)
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

// ========== 工具函数 ==========
function formatYMD(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function pad(n: number) { return n < 10 ? `0${n}` : `${n}` }

// ========== 月份切换 ==========
function prevMonth() {
  if (viewMonth.value === 1) { viewYear.value--; viewMonth.value = 12 }
  else { viewMonth.value-- }
  fetchData()
}
function nextMonth() {
  if (viewMonth.value === 12) { viewYear.value++; viewMonth.value = 1 }
  else { viewMonth.value++ }
  fetchData()
}
function gotoToday() {
  viewYear.value = today.getFullYear()
  viewMonth.value = today.getMonth() + 1
  fetchData()
}

// ========== 日历网格 ==========
const calendarCells = computed(() => {
  const firstDay = new Date(viewYear.value, viewMonth.value - 1, 1)
  const firstWeekday = (firstDay.getDay() + 6) % 7
  const daysInMonth = new Date(viewYear.value, viewMonth.value, 0).getDate()

  const map = new Map<string, { staff_name: string; shift_type: string }[]>()
  scheduleList.value.forEach(s => {
    const key = s.shift_date
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push({ staff_name: s.staff_name, shift_type: s.shift_type })
  })

  const prevMonthDays = new Date(viewYear.value, viewMonth.value - 1, 0).getDate()
  const cells: Array<{
    date: string; day: number; inMonth: boolean; isToday: boolean; isWeekend: boolean;
    shifts: { staff_name: string; shift_type: string }[]
  }> = []

  for (let i = 0; i < firstWeekday; i++) {
    cells.push({
      date: '', day: prevMonthDays - firstWeekday + i + 1, inMonth: false,
      isToday: false, isWeekend: false, shifts: [],
    })
  }

  const todayStr = formatYMD(today)
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${viewYear.value}-${pad(viewMonth.value)}-${pad(d)}`
    const dt = new Date(viewYear.value, viewMonth.value - 1, d)
    const w = (dt.getDay() + 6) % 7
    cells.push({
      date: dateStr,
      day: d,
      inMonth: true,
      isToday: dateStr === todayStr,
      isWeekend: w >= 5,
      shifts: map.get(dateStr) || [],
    })
  }

  const totalCells = Math.ceil(cells.length / 7) * 7
  let nextDay = 1
  while (cells.length < totalCells) {
    cells.push({
      date: '', day: nextDay++, inMonth: false, isToday: false, isWeekend: false, shifts: [],
    })
  }

  return cells
})

// ========== 点击日期格 ==========
function onCellClick(cell: { date: string; inMonth: boolean; shifts: { staff_name: string; shift_type: string }[] }) {
  if (!cell.inMonth || !cell.date) return
  // 有排班则弹出详情，无排班则填入快速排班
  if (cell.shifts.length > 0) {
    showDayDetail(cell)
  } else {
    quickForm.value.shift_date = cell.date
    quickMsg.value = `已选择 ${cell.date}，请选择人员和班次`
    quickErr.value = false
    setTimeout(() => { if (quickMsg.value === `已选择 ${cell.date}，请选择人员和班次`) quickMsg.value = '' }, 2500)
  }
}

// ========== 点击已排班人员 → 删除或切换 ==========
async function onShiftClick(e: MouseEvent, cell: { date: string; shifts: { staff_name: string; shift_type: string }[] }, shift: { staff_name: string; shift_type: string }) {
  e.stopPropagation()
  const choice = window.prompt(
    `${shift.staff_name} 在 ${cell.date} 的班次：${shift.shift_type}\n\n输入选项：\n1 - 修改为早班\n2 - 修改为下午班\n3 - 修改为晚班\n4 - 修改为休息\n5 - 删除`,
    '5'
  )
  if (!choice) return
  const idx = parseInt(choice)
  if (idx === 5) {
    if (!confirm(`确认删除 ${shift.staff_name} 在 ${cell.date} 的排班？`)) return
    await axios.post(`${API}/api/staff/schedule/delete`, {
      staff_name: shift.staff_name, shift_date: cell.date,
    }).catch(() => null)
  } else {
    const map: Record<number, string> = { 1: '早班', 2: '晚班', 3: '休息' }
    const newType = map[idx]
    if (!newType || newType === shift.shift_type) return
    await axios.post(`${API}/api/staff/schedule`, {
      staff_name: shift.staff_name, shift_date: cell.date, shift_type: newType,
    })
  }
  fetchData()
  // 更新弹窗数据
  if (dayDetail.value && dayDetail.value.date === cell.date) {
    const updated = cell.shifts.filter(s => !(s.staff_name === shift.staff_name && (idx === 5)))
    if (updated.length) {
      dayDetail.value.shifts = updated
    } else {
      closeDayDetail()
    }
  }
}

// ========== 班次颜色 ==========
function shiftClass(type: string) {
  return shiftInfoMap[type]?.cssClass || ''
}

// ========== 保存排班 ==========
async function saveQuickSchedule() {
  quickMsg.value = ''
  quickErr.value = false
  if (!quickForm.value.staff_name || !quickForm.value.shift_date) {
    quickMsg.value = '请选择人员和日期'; quickErr.value = true; return
  }
  try {
    const res = await axios.post(`${API}/api/staff/schedule`, {
      staff_name: quickForm.value.staff_name,
      shift_date: quickForm.value.shift_date,
      shift_type: quickForm.value.shift_type,
    })
    if (res.data.ok) {
      quickMsg.value = `${quickForm.value.staff_name} ${quickForm.value.shift_date} 已设为「${quickForm.value.shift_type}」`
      quickErr.value = false
      fetchData()
      setTimeout(() => { quickMsg.value = '' }, 3000)
    } else {
      quickMsg.value = res.data.reason || '保存失败'; quickErr.value = true
    }
  } catch (e: any) {
    quickMsg.value = e?.response?.data?.reason || '保存失败'; quickErr.value = true
  }
}

// ========== 批量排班 ==========
function toggleWeekday(idx: number) {
  const i = batchForm.value.weekdays.indexOf(idx)
  if (i >= 0) batchForm.value.weekdays.splice(i, 1)
  else batchForm.value.weekdays.push(idx)
}
function toggleStaff(name: string) {
  const i = batchForm.value.staff_names.indexOf(name)
  if (i >= 0) batchForm.value.staff_names.splice(i, 1)
  else batchForm.value.staff_names.push(name)
}
function selectAllStaff() {
  batchForm.value.staff_names = [...allStaff.value]
}
function clearAllStaff() {
  batchForm.value.staff_names = []
}
function onBatchDateChange(field: 'start' | 'end') {
  if (batchForm.value.start_date && batchForm.value.end_date) {
    if (batchForm.value.end_date < batchForm.value.start_date) {
      batchMsg.value = '结束日期不能早于开始日期'
      batchErr.value = true
      if (field === 'end') batchForm.value.end_date = ''
      else batchForm.value.start_date = ''
      setTimeout(() => { batchMsg.value = '' }, 3000)
      return
    }
  }
  batchMsg.value = ''
  batchErr.value = false
}
async function saveBatch() {
  batchMsg.value = ''; batchErr.value = false
  if (!batchForm.value.staff_names.length) {
    batchMsg.value = '请选择至少一个人员'; batchErr.value = true; return
  }
  if (!batchForm.value.weekdays.length) {
    batchMsg.value = '请选择至少一个星期几'; batchErr.value = true; return
  }
  if (!batchForm.value.start_date || !batchForm.value.end_date) {
    batchMsg.value = '请选择起止日期'; batchErr.value = true; return
  }
  if (batchForm.value.start_date > batchForm.value.end_date) {
    batchMsg.value = '开始日期不能晚于结束日期'; batchErr.value = true; return
  }
  try {
    const res = await axios.post(`${API}/api/staff/schedule/batch`, batchForm.value)
    if (res.data.ok) {
      batchMsg.value = `已生成 ${res.data.count} 条排班记录`
      batchErr.value = false
      fetchData()
      setTimeout(() => { batchMsg.value = '' }, 3000)
    } else {
      batchMsg.value = res.data.reason || '批量排班失败'; batchErr.value = true
    }
  } catch (e: any) {
    batchMsg.value = e?.response?.data?.reason || '批量排班失败'; batchErr.value = true
  }
}

onMounted(() => {
  fetchData()
  window.addEventListener('schedule-refresh', fetchData)
})
onUnmounted(() => {
  window.removeEventListener('schedule-refresh', fetchData)
})
</script>

<template>
  <div class="schedule-page">
    <!-- ======== 顶部：标题 + 刷新 ======== -->
    <div class="page-topbar">
      <h2 class="page-title">值班排班管理</h2>
      <button class="btn-refresh" @click="fetchData" :disabled="loading">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" :class="{ spinning: loading }">
          <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
        </svg>
        刷新
      </button>
    </div>

    <!-- ======== KPI 卡片 ======== -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-icon-wrap" style="--kpi-color: #3b82f6">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/><line x1="8" y1="21" x2="8" y2="9"/>
          </svg>
        </div>
        <div class="kpi-info">
          <span class="kpi-value">{{ kpi.today_on_duty }}</span>
          <span class="kpi-label">今日值班</span>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon-wrap" style="--kpi-color: #10b981">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="8" r="4"/><path d="M5.3 18.3C6.8 16.5 9.2 15.2 12 15.2s5.2 1.3 6.7 3.1"/>
          </svg>
        </div>
        <div class="kpi-info">
          <span class="kpi-value">{{ kpi.online_count }}</span>
          <span class="kpi-label">当前在线</span>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon-wrap" style="--kpi-color: #8b5cf6">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <div class="kpi-info">
          <span class="kpi-value">{{ kpi.month_total_shifts }}</span>
          <span class="kpi-label">本月排班次</span>
        </div>
      </div>
    </div>

    <!-- ======== 日历区 ======== -->
    <div class="card calendar-card">
      <div class="cal-header">
        <div class="cal-nav">
          <button class="nav-arrow" @click="prevMonth" title="上月">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
          <h3 class="cal-month-label">{{ viewYear }} 年 {{ viewMonth }} 月</h3>
          <button class="nav-arrow" @click="nextMonth" title="下月">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
          </button>
          <button class="btn-today" @click="gotoToday">今天</button>
        </div>
        <div class="cal-legend">
          <span class="legend-item"><span class="legend-dot morning"></span>早班 08:30-11:30</span>
          <span class="legend-item"><span class="legend-dot afternoon"></span>下午班 14:00-18:00</span>
          <span class="legend-item"><span class="legend-dot evening"></span>晚班 20:00-22:00</span>
        </div>
      </div>

      <!-- 星期表头 -->
      <div class="cal-weekdays">
        <div v-for="w in weekdayLabels" :key="w" class="cal-wd" :class="{ weekend: ['六','日'].includes(w) }">
          周{{ w }}
        </div>
      </div>

      <!-- 日历格子 -->
      <div class="cal-grid">
        <div
          v-for="(cell, i) in calendarCells"
          :key="i"
          class="cal-cell"
          :class="{
            'is-out': !cell.inMonth,
            'is-today': cell.isToday,
            'is-weekend': cell.isWeekend && cell.inMonth,
            'has-shifts': cell.shifts.filter(s => s.shift_type !== '休息').length > 0 && cell.inMonth,
          }"
          @click="onCellClick(cell)"
        >
          <span class="cell-date">{{ cell.day }}</span>
          <div v-if="cell.inMonth" class="cell-shifts">
            <div
              v-for="st in dutyShiftTypes"
              :key="st"
              class="shift-slot"
              :class="shiftInfoMap[st].cssClass"
              @click="showDayDetail(cell)"
            >
              <span class="slot-name">{{ st }}{{ cell.shifts.filter(s => s.shift_type === st).length ? '（'+cell.shifts.filter(s => s.shift_type === st).length+'人）' : '' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ======== 日期详情弹窗 ======== -->
    <Teleport to="body">
      <div v-if="dayDetail" class="modal-overlay" @click.self="closeDayDetail">
        <div class="modal-card">
          <div class="modal-head">
            <div class="modal-title-row">
              <h3 class="modal-title">{{ dayDetail.date }}</h3>
              <span class="modal-weekday">{{ dayDetail.dayOfWeek }}</span>
            </div>
            <button class="modal-close" @click="closeDayDetail">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div class="modal-body">
            <div v-if="dayDetail.shifts.filter(s => s.shift_type !== '休息').length === 0" class="modal-empty">当日暂无上班人员</div>
            <div v-else class="detail-groups">
              <div v-for="st in dutyShiftTypes" :key="st" class="detail-group">
                <div v-if="dayDetail.shifts.filter(s => s.shift_type === st).length > 0">
                  <div class="detail-group-head" :class="shiftInfoMap[st].cssClass">
                    <span class="group-shift-name">{{ st }}</span>
                    <span class="group-shift-time">{{ shiftInfoMap[st].time }}</span>
                  </div>
                  <div class="detail-items">
                    <div v-for="s in dayDetail.shifts.filter(s => s.shift_type === st)" :key="s.staff_name" class="detail-item">
                      <div class="detail-avatar">{{ s.staff_name.charAt(0) }}</div>
                      <span class="detail-name">{{ s.staff_name }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ======== 快速排班 ======== -->
    <div class="card quick-card">
      <div class="card-head">
        <h3 class="card-title">快速排班</h3>
        <span class="card-hint">点击有排班的日期可查看详情，点击空日期可快速填入</span>
      </div>
      <div class="quick-form">
        <div class="form-fields">
          <div class="field">
            <label>人员</label>
            <select v-model="quickForm.staff_name" class="input">
              <option v-for="n in allStaff" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>
          <div class="field">
            <label>日期</label>
            <div class="date-input-wrap">
              <input type="date" v-model="quickForm.shift_date" class="input date-input" :class="{ 'is-empty': !quickForm.shift_date }" />
              <span v-if="!quickForm.shift_date" class="date-placeholder">例:2000-01-01</span>
              <span v-else class="date-display">{{ quickForm.shift_date }}</span>
              <svg class="date-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
            </div>
          </div>
          <div class="field">
            <label>班次</label>
            <div class="shift-toggles">
              <button
                v-for="s in shiftOptions" :key="s"
                class="shift-opt"
                :class="[
                  { active: quickForm.shift_type === s },
                  shiftInfoMap[s].cssClass
                ]"
                @click="quickForm.shift_type = s"
              >{{ s }}</button>
            </div>
          </div>
          <div class="field field-actions">
            <label>&nbsp;</label>
            <div class="action-btns">
              <button class="btn-save" @click="saveQuickSchedule">保存排班</button>
              <button class="btn-toggle-batch" @click="showBatch = !showBatch">
                {{ showBatch ? '收起批量' : '批量排班' }}
              </button>
            </div>
          </div>
        </div>
        <p v-if="quickMsg" class="feedback-msg" :class="{ error: quickErr }">
          <svg v-if="!quickErr" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
          <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          {{ quickMsg }}
        </p>
      </div>

      <!-- 批量排班 -->
      <div v-if="showBatch" class="batch-section">
        <div class="batch-head">
          <div class="batch-head-left">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
            <span>批量排班</span>
          </div>
          <span class="batch-hint">填写条件后，系统将在范围内按所选星期自动生成排班</span>
        </div>

        <!-- 人员选择 -->
        <div class="batch-group">
          <label class="batch-label">选择人员</label>
          <div class="pill-group">
            <button
              v-for="n in allStaff" :key="n"
              class="pill" :class="{ active: batchForm.staff_names.includes(n) }"
              @click="toggleStaff(n)"
            >{{ n }}</button>
            <button class="pill pill-ctrl" @click="selectAllStaff">全选</button>
            <button class="pill pill-ctrl" @click="clearAllStaff">清空</button>
          </div>
        </div>

        <!-- 日期范围 + 星期 + 班次 -->
        <div class="batch-group">
          <label class="batch-label">排班条件</label>
          <div class="batch-conditions">
            <div class="field">
              <label class="field-sub">起始</label>
              <div class="date-input-wrap">
                <input type="date" v-model="batchForm.start_date" class="input date-input" :class="{ 'is-empty': !batchForm.start_date }" :max="batchForm.end_date || undefined" @change="onBatchDateChange('start')" />
                <span v-if="!batchForm.start_date" class="date-placeholder">例:2000-01-01</span>
                <span v-else class="date-display">{{ batchForm.start_date }}</span>
              </div>
            </div>
            <span class="batch-sep">至</span>
            <div class="field">
              <label class="field-sub">结束</label>
              <div class="date-input-wrap">
                <input type="date" v-model="batchForm.end_date" class="input date-input" :class="{ 'is-empty': !batchForm.end_date }" :min="batchForm.start_date || undefined" @change="onBatchDateChange('end')" />
                <span v-if="!batchForm.end_date" class="date-placeholder">例:2000-12-31</span>
                <span v-else class="date-display">{{ batchForm.end_date }}</span>
              </div>
            </div>
            <div class="field">
              <label class="field-sub">星期</label>
              <div class="pill-group">
                <button
                  v-for="(w, i) in weekdayLabels" :key="w"
                  class="pill pill-sm" :class="{ active: batchForm.weekdays.includes(i) }"
                  @click="toggleWeekday(i)"
                >{{ w }}</button>
              </div>
            </div>
            <div class="field">
              <label class="field-sub">班次</label>
              <div class="shift-toggles">
                <button
                  v-for="s in shiftOptions" :key="s"
                  class="shift-opt"
                  :class="[
                    { active: batchForm.shift_type === s },
                    shiftInfoMap[s].cssClass
                  ]"
                  @click="batchForm.shift_type = s"
                >{{ s }}</button>
              </div>
            </div>
          </div>
        </div>

        <p v-if="batchMsg" class="feedback-msg" :class="{ error: batchErr }">
          <svg v-if="!batchErr" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
          <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          {{ batchMsg }}
        </p>
        <button class="btn-save-batch" @click="saveBatch">执行批量排班</button>
      </div>
    </div>

    <!-- 加载遮罩 -->
    <div v-if="loading" class="loading-overlay">
      <span class="loading-spinner"></span>
      <span>加载中...</span>
    </div>
  </div>
</template>

<style scoped>
/* ================= 基础变量 ================= */
.schedule-page {
  --bg: #f1f5f9;
  --surface: #ffffff;
  --text: #0f172a;
  --text-sec: #475569;
  --text-muted: #94a3b8;
  --border: #e2e8f0;
  --border-light: #f1f5f9;
  --blue: #3b82f6;
  --blue-light: #eff6ff;
  --green: #10b981;
  --purple: #8b5cf6;
  --red: #ef4444;
  --morning: #1677FF;        /* 早班：标准蓝 */
  --morning-text: #1677FF;
  --morning-soft: rgba(22, 119, 255, 0.06);
  --afternoon: #FAAD14;      /* 下午班：亮橙 */
  --afternoon-text: #FAAD14;
  --afternoon-soft: rgba(250, 173, 20, 0.06);
  --evening: #722ED1;        /* 晚班：紫罗兰 */
  --evening-text: #722ED1;
  --evening-soft: rgba(114, 46, 209, 0.06);
  --off: #94a3b8;            /* 休息：石板灰 */
  --off-soft: #f8fafc;
  --radius: 12px;
  --radius-sm: 8px;

  font-family: "Microsoft YaHei", "微软雅黑", -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--text);
  position: relative;
}

/* ================= 顶部栏 ================= */
.page-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.3px;
}
.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-sec);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-refresh:hover {
  border-color: var(--blue);
  color: var(--blue);
  background: var(--blue-light);
}
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ================= KPI 卡片 ================= */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 20px 22px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  transition: box-shadow 0.2s;
}
.kpi-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.kpi-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--kpi-color);
  background: color-mix(in srgb, var(--kpi-color) 10%, transparent);
}
.kpi-info { display: flex; flex-direction: column; }
.kpi-value {
  font-size: 28px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.kpi-label {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* ================= 通用卡片 ================= */
.card {
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  margin-bottom: 20px;
  overflow: hidden;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px 0;
}
.card-title { margin: 0; font-size: 15px; font-weight: 600; color: var(--text); }
.card-hint { font-size: 12px; color: var(--text-muted); }

/* ================= 日历区 ================= */
.calendar-card { padding: 0; }

.cal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px 14px;
  border-bottom: 1px solid var(--border-light);
}
.cal-nav { display: flex; align-items: center; gap: 6px; }
.cal-month-label {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  min-width: 120px;
  text-align: center;
}
.nav-arrow {
  width: 30px; height: 30px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface); color: var(--text-sec);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.nav-arrow:hover { background: #f8fafc; border-color: #cbd5e1; }
.btn-today {
  padding: 5px 14px; margin-left: 4px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface); color: var(--text-sec);
  font-size: 12px; cursor: pointer;
  transition: all 0.15s;
}
.btn-today:hover { background: var(--text); color: #fff; border-color: var(--text); }

.cal-legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-sec); }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.legend-dot {
  width: 8px; height: 8px; border-radius: 3px; display: inline-block;
}
.legend-dot.morning { background: var(--morning); }
.legend-dot.afternoon { background: var(--afternoon); }
.legend-dot.evening { background: var(--evening); }

/* 星期表头 */
.cal-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  padding: 0 8px;
  margin: 8px 0 4px;
}
.cal-wd {
  text-align: center;
  font-size: 12px; font-weight: 600;
  color: var(--text-sec);
  padding: 8px 0; border-radius: 4px;
  background: #f8fafc;
  margin: 0 2px;
}
.cal-wd.weekend { color: var(--red); }

/* 日历格子 — 极简指示线风格 */
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
  padding: 0 8px 12px;
}
.cal-cell {
  min-height: 88px;
  background: #ffffff;
  border: 1px solid #e8ecf1;
  border-radius: 6px;
  padding: 8px 8px 6px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  display: flex; flex-direction: column; gap: 4px;
  position: relative;
}
.cal-cell:hover { background: #f9fafb; border-color: #d0d5dd; }
.cal-cell.is-out {
  background: #fafbfc; color: #c5cad3; cursor: default;
  border-color: #f0f1f3;
}
.cal-cell.is-out:hover { background: #fafbfc; border-color: #f0f1f3; }
.cal-cell.is-weekend { background: #fdfdfe; }
.cal-cell.is-today {
  background: #ffffff;
  border-color: var(--blue);
  box-shadow: inset 0 0 0 1.5px var(--blue);
}
.cell-date {
  font-size: 13px; font-weight: 600;
  color: #64748b; line-height: 1;
  margin-bottom: 2px;
}
.cal-cell.is-out .cell-date { color: #c5cad3; }
.cal-cell.is-today .cell-date { color: var(--blue); }

/* 排班条目容器 */
.cell-shifts {
  display: flex; flex-direction: column;
  gap: 4px;
}

/* 排班条目 — 左侧指示线 + 右侧文字 */
.shift-slot {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 2px 6px 2px 0;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
  min-height: 18px;
}
.shift-slot:hover { background: #f5f5f5; }

/* 左侧彩色指示线 */
.shift-slot::before {
  content: '';
  width: 3px;
  height: 100%;
  min-height: 16px;
  border-radius: 2px;
  flex-shrink: 0;
  margin-right: 8px;
  align-self: stretch;
}
.shift-slot.morning::before { background: var(--morning); }
.shift-slot.afternoon::before { background: var(--afternoon); }
.shift-slot.evening::before { background: var(--evening); }
.shift-slot.off::before { background: var(--off); }

/* 班次文字 */
.slot-name {
  font-size: 11px; font-weight: 500;
  color: #333333;
  white-space: nowrap;
  line-height: 1.3;
  flex: 1;
}

/* ================= 日期详情弹窗 ================= */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.3);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.modal-card {
  background: var(--surface);
  border-radius: 16px;
  width: 420px;
  max-width: 90vw;
  max-height: 70vh;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
  overflow: hidden;
  animation: slideUp 0.25s ease;
}
@keyframes slideUp { from { opacity: 0; transform: translateY(24px); } to { opacity: 1; transform: translateY(0); } }

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border-light);
}
.modal-title-row { display: flex; align-items: baseline; gap: 10px; }
.modal-title { margin: 0; font-size: 18px; font-weight: 600; color: var(--text); }
.modal-weekday { font-size: 13px; color: var(--text-muted); }
.modal-close {
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: transparent; color: var(--text-muted);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.modal-close:hover { background: var(--border-light); color: var(--text); }

.modal-body { padding: 16px 24px 24px; overflow-y: auto; max-height: 50vh; }
.modal-empty {
  text-align: center; padding: 32px 0;
  color: var(--text-muted); font-size: 14px;
}

.detail-list { display: flex; flex-direction: column; gap: 8px; }

/* 详情弹窗：按班次分组 */
.detail-groups { display: flex; flex-direction: column; gap: 16px; }
.detail-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 8px 14px;
  border-radius: 6px;
  margin-bottom: 6px;
  background: #fafbfc;
  border-left: 3px solid transparent;
}
.detail-group-head.morning { border-left-color: var(--morning); }
.detail-group-head.afternoon { border-left-color: var(--afternoon); }
.detail-group-head.evening { border-left-color: var(--evening); }
.group-shift-name {
  font-size: 14px; font-weight: 600;
  color: #333333;
}
.group-shift-time {
  font-size: 12px; font-weight: 400;
  color: var(--text-muted);
}
.detail-items { display: flex; flex-direction: column; gap: 4px; }
.detail-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  background: #f8fafc;
  border-radius: 6px;
}
.detail-avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: var(--blue-light);
  color: var(--blue);
  font-size: 12px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.detail-name { font-size: 13px; font-weight: 500; color: var(--text); }

/* ================= 快速排班区 ================= */
.quick-card { padding-bottom: 20px; }
.quick-form { padding: 14px 24px 0; }

.form-fields {
  display: flex;
  gap: 14px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.field {
  display: flex; flex-direction: column;
  gap: 5px; min-width: 130px; flex: 1;
}
.field label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
.field-actions { flex: 0 0 auto; min-width: 0; }

.input {
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px; outline: none;
  background: #f8fafc; color: var(--text);
  transition: border-color 0.2s, background 0.2s;
  width: 100%; box-sizing: border-box;
}
.input:focus { border-color: var(--blue); background: var(--surface); }

.date-input-wrap { position: relative; }
.date-input-wrap .input { padding-right: 32px; }
.date-input {
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  outline: none;
  color: #334155;
  transition: border-color 0.2s, box-shadow 0.2s;
  width: 100%; box-sizing: border-box;
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
  border-color: var(--blue);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
  background: #fff;
}
/* 隐藏空的或已选的原生日期文字 */
.date-input.is-empty::-webkit-datetime-edit,
.date-input.is-empty::-webkit-datetime-edit-fields-wrapper,
.date-input.is-empty::-webkit-datetime-edit-text,
.date-input.is-empty::-webkit-datetime-edit-month-field,
.date-input.is-empty::-webkit-datetime-edit-day-field,
.date-input.is-empty::-webkit-datetime-edit-year-field {
  color: transparent;
}
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
.date-icon {
  position: absolute; right: 10px; top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted); pointer-events: none;
}

.shift-toggles { display: flex; gap: 5px; }
.shift-opt {
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: 13px; color: var(--text-sec);
  cursor: pointer;
  transition: all 0.15s; white-space: nowrap;
}
.shift-opt:hover { background: #f8fafc; }
.shift-opt.morning.active { background: var(--morning); color: #fff; border-color: var(--morning); }
.shift-opt.afternoon.active { background: var(--afternoon); color: #fff; border-color: var(--afternoon); }
.shift-opt.evening.active { background: var(--evening); color: #fff; border-color: var(--evening); }
.shift-opt.off.active { background: var(--off); color: #fff; border-color: var(--off); }

.action-btns { display: flex; gap: 8px; }
.btn-save {
  padding: 9px 20px;
  border: none; border-radius: var(--radius-sm);
  background: var(--blue);
  color: #fff; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background 0.15s; white-space: nowrap;
}
.btn-save:hover { background: #2563eb; }
.btn-toggle-batch {
  padding: 9px 14px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--text-sec);
  font-size: 13px; cursor: pointer;
  transition: all 0.15s; white-space: nowrap;
}
.btn-toggle-batch:hover { background: #f8fafc; border-color: #cbd5e1; }

/* 反馈消息 */
.feedback-msg {
  display: inline-flex; align-items: center; gap: 6px;
  margin: 10px 0 0;
  font-size: 13px; font-weight: 500;
  color: var(--green);
}
.feedback-msg.error { color: var(--red); }

/* ================= 批量排班（美化版） ================= */
.pill-group { display: flex; flex-wrap: wrap; gap: 6px; }
.pill {
  padding: 6px 12px;
  border: 1px solid var(--border); border-radius: 16px;
  background: var(--surface); font-size: 12px; color: var(--text-sec);
  cursor: pointer; transition: all 0.15s;
}
.pill:hover { border-color: var(--blue); color: var(--blue); }
.pill.active { background: var(--blue); color: #fff; border-color: var(--blue); }
.pill-ctrl { color: var(--text-muted); font-size: 11px; }
.pill-ctrl:hover { color: var(--text-sec); border-color: var(--text-sec); }

.batch-section {
  margin: 8px 20px 20px;
  padding: 20px;
  background: #f8fafc;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  animation: slideDown 0.25s ease-out;
}
@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }

.batch-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.batch-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px; font-weight: 600;
  color: var(--text);
}
.batch-head-left svg { color: var(--blue); }
.batch-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.batch-group {
  margin-bottom: 16px;
}
.batch-group:last-of-type { margin-bottom: 0; }
.batch-label {
  display: block;
  font-size: 12px; font-weight: 600;
  color: var(--text-sec);
  margin-bottom: 8px;
  text-transform: none;
  letter-spacing: 0.3px;
}

.batch-conditions {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}
.batch-sep {
  font-size: 13px;
  color: var(--text-muted);
  padding-bottom: 8px;
}
.field-sub {
  font-size: 11px !important;
  color: var(--text-muted) !important;
  font-weight: 500 !important;
}

.pill-sm {
  padding: 4px 10px !important;
  font-size: 11px !important;
}

.btn-save-batch {
  margin-top: 16px;
  padding: 9px 24px;
  border: none; border-radius: var(--radius-sm);
  background: var(--blue);
  color: #fff; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background 0.15s;
}
.btn-save-batch:hover { background: #2563eb; }

/* ================= 加载遮罩 ================= */
.loading-overlay {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px;
  background: rgba(241, 245, 249, 0.8);
  backdrop-filter: blur(4px);
  border-radius: var(--radius);
  z-index: 10;
  font-size: 14px; color: var(--text-sec);
}
.loading-spinner {
  width: 28px; height: 28px;
  border: 3px solid var(--border);
  border-top-color: var(--blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ================= 响应式 ================= */
@media (max-width: 1024px) {
  .kpi-row { grid-template-columns: 1fr; }
  .form-fields { flex-direction: column; }
  .field { min-width: 100%; }
}
@media (max-width: 768px) {
  .cal-header { flex-direction: column; gap: 12px; align-items: flex-start; }
  .cal-cell { min-height: 70px; padding: 4px; }
  .shift-slot { padding: 1px 2px; }
  .slot-name { font-size: 9px; }
}
</style>