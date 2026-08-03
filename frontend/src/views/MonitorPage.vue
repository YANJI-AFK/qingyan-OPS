<script setup lang="ts">
import { ref, onMounted, onUnmounted, shallowRef } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import * as echarts from 'echarts';
import MonitorChart from '../components/MonitorChart.vue';
import CenterHologramGlobe from '../components/CenterHologramGlobe.vue';

const router = useRouter();

const timeData = ref<string[]>([]);
const cpuData = ref<number[]>([]);
const memData = ref<number[]>([]);
// 4 个节点的独立内存数据（用于左侧"节点 01-04"进度条展示）
const nodeMemData = ref<number[]>([65, 72, 58, 81]);
const diskReadData = ref<number[]>([]);
const diskWriteData = ref<number[]>([]);
const netInData = ref<number[]>([]);
const netOutData = ref<number[]>([]);

// 顶部动态指标（随机游走）
const eventIntercept = ref(14205);
const activeNodes = ref(2048);
const ticketDone = ref(892);
let lastEvent = 14205, lastNodes = 2048, lastTickets = 892;

const currentTime = ref('');
let clockTimer: ReturnType<typeof setInterval>;
const updateTime = () => {
  const now = new Date();
  currentTime.value = now.toLocaleDateString() + ' ' + now.toLocaleTimeString();
};

const topoChartRef = ref<HTMLElement | null>(null);
const pieChartRef = ref<HTMLElement | null>(null);
const topoInstance = shallowRef<echarts.ECharts | null>(null);
const pieInstance = shallowRef<echarts.ECharts | null>(null);

const initTopoChart = () => {
  if (!topoChartRef.value) return;
  topoInstance.value = echarts.init(topoChartRef.value);
  topoInstance.value.setOption({
    tooltip: { formatter: '{b}' },
    series: [
      {
        type: 'graph',
        layout: 'force',
        force: { repulsion: 400, edgeLength: [90, 180], gravity: 0.1 },
        roam: false,
        draggable: false,
        label: {
          show: true,
          position: 'right',
          color: '#99bcdd',
          fontSize: 11,
          distance: 8
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        itemStyle: { color: '#0d1b2e', borderColor: '#3a6b8c', borderWidth: 1.5, borderType: 'solid' },
        lineStyle: { color: '#3a6b8c', width: 1.5, curveness: 0.15, opacity: 0.6 },
        data: [
          { name: '决策层',   category: 0, symbolSize: 44, itemStyle: { color: '#1a3a5c', borderColor: '#5b9bd5' } },
          { name: '运维中心', category: 1, symbolSize: 32 },
          { name: '安全部',   category: 1, symbolSize: 32 },
          { name: '开发组',   category: 1, symbolSize: 32 },
          { name: '监控节点', category: 2, symbolSize: 26 },
          { name: '审计日志', category: 2, symbolSize: 26 },
          { name: '发布流水线', category: 2, symbolSize: 26 },
          { name: '边缘网关', category: 2, symbolSize: 26 },
        ],
        links: [
          { source: '决策层', target: '运维中心' },
          { source: '决策层', target: '安全部' },
          { source: '决策层', target: '开发组' },
          { source: '运维中心', target: '监控节点' },
          { source: '运维中心', target: '边缘网关' },
          { source: '安全部', target: '审计日志' },
          { source: '开发组', target: '发布流水线' },
        ],
        categories: [
          { name: '核心' },
          { name: '部门' },
          { name: '服务' },
        ]
      }
    ]
  });
};

const initPieChart = () => {
  if (!pieChartRef.value) return;
  pieInstance.value = echarts.init(pieChartRef.value);

  pieInstance.value.setOption({
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} GB ({d}%)',
      backgroundColor: 'rgba(2, 8, 19, 0.9)',
      borderColor: '#00f3ff',
      textStyle: { color: '#fff' }
    },
    legend: {
      orient: 'vertical',
      right: 8,
      top: 'middle',
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 10,
      textStyle: { color: '#88bbff', fontSize: 11 }
    },
    xAxis3D: { min: -1, max: 1 },
    yAxis3D: { min: -1, max: 1 },
    zAxis3D: { min: -1, max: 1 },
    grid3D: {
      show: false,
      boxWidth: 60,
      boxDepth: 60,
      boxHeight: 20,
      viewControl: {
        alpha: 40,
        beta: 30,
        rotateSensitivity: 0,
        zoomSensitivity: 0
      }
    },
    series: [
      {
        type: 'pie',
        radius: ['38%', '58%'],
        center: ['32%', '50%'],
        roseType: false,
        itemStyle: {
          borderColor: '#010409',
          borderWidth: 2,
          opacity: 0.9
        },
        label: {
          show: true,
          position: 'outside',
          formatter: '{b}\n{c}GB ({d}%)',
          color: '#00f3ff',
          fontSize: 10,
          fontWeight: 'bold',
          edgeDistance: 4
        },
        labelLine: {
          show: true,
          length: 6,
          length2: 8,
          lineStyle: { color: '#00f3ff', width: 1 }
        },
        data: [
          { value: 65, name: 'SSD 热点', itemStyle: { color: '#0d4f6b' } },
          { value: 25, name: 'HDD 温备', itemStyle: { color: '#1d5c3a' } },
          { value: 10, name: '冷归档', itemStyle: { color: '#5c1d4a' } }
        ]
      }
    ]
  });
};

let pollTimer: ReturnType<typeof setInterval>;
let topoFlashTimer: ReturnType<typeof setInterval>;

// 随机游走基准值
let rwCpu = 65, rwMem = 70, rwDiskR = 42, rwDiskW = 30, rwNetIn = 110, rwNetOut = 85;
// 随机游走种子
function seededRandom(seed: number) { return () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; } }
const rng = seededRandom(Date.now() % 10000 + 1);

const MAX_POINTS = 200;

function rwalk(val: number, range: number, min: number, max: number) {
  return Math.max(min, Math.min(max, val + (rng() - 0.5) * range));
}

const fetchMetrics = () => {
  // 实时生成新数据点（随机游走模拟真实服务器波动）
  rwCpu = rwalk(rwCpu, 6, 15, 95);
  rwMem = rwalk(rwMem, 4, 20, 92);
  rwDiskR = rwalk(rwDiskR, 8, 5, 90);
  rwDiskW = rwalk(rwDiskW, 6, 3, 70);
  rwNetIn = rwalk(rwNetIn, 16, 20, 200);
  rwNetOut = rwalk(rwNetOut, 12, 15, 180);

  const now = new Date();
  const secs = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();

  // 叠加周期性波动（让数据有日间节奏感）
  const waveCpu = rwCpu + Math.sin(secs * 0.03) * 3;
  const waveMem = rwMem + Math.sin(secs * 0.025 + 1) * 2;
  const waveDiskR = rwDiskR + Math.sin(secs * 0.02 + 2) * 5;
  const waveDiskW = rwDiskW + Math.sin(secs * 0.028 + 3) * 4;
  const waveNetIn = rwNetIn + Math.sin(secs * 0.04) * 8;
  const waveNetOut = rwNetOut + Math.sin(secs * 0.035 + 3) * 6;

  const ts = now.toLocaleTimeString();
  timeData.value.push(ts);
  cpuData.value.push(Number(waveCpu.toFixed(1)));
  memData.value.push(Number(waveMem.toFixed(1)));
  // 4 个节点内存数据独立随机游走
  nodeMemData.value = nodeMemData.value.map((v, i) => {
    const range = [5, 4, 6, 3][i]
    const min = [50, 55, 48, 60][i]
    const max = [90, 88, 92, 95][i]
    return Number(rwalk(v, range, min, max).toFixed(1))
  })
  diskReadData.value.push(Number(waveDiskR.toFixed(1)));
  diskWriteData.value.push(Number(waveDiskW.toFixed(1)));
  netInData.value.push(Number(waveNetIn.toFixed(1)));
  netOutData.value.push(Number(waveNetOut.toFixed(1)));

  // 超过最大点数时移除最早的数据
  if (timeData.value.length > MAX_POINTS) {
    timeData.value.shift(); cpuData.value.shift(); memData.value.shift();
    diskReadData.value.shift(); diskWriteData.value.shift();
    netInData.value.shift(); netOutData.value.shift();
  }

  // 顶部三指标持续波动（活跃节点区间更大更显变化）
  lastEvent = Math.max(10000, lastEvent + (rng() - 0.5) * 120);
  lastNodes = Math.max(1500, lastNodes + (rng() - 0.5) * 60);
  lastTickets = Math.max(500, lastTickets + (rng() - 0.5) * 25);
  eventIntercept.value = Math.round(lastEvent);
  activeNodes.value = Math.round(lastNodes);
  ticketDone.value = Math.round(lastTickets);
};

// 拓扑图节点动态闪烁
const topoNodes = ['决策层', '运维中心', '安全部', '开发组', '监控节点', '审计日志', '发布流水线', '边缘网关'];
function animateTopo() {
  if (!topoInstance.value || topoInstance.value.isDisposed()) return;
  // 随机选1-2个节点临时放大再恢复，制造动态感
  const idx = Math.floor(rng() * topoNodes.length);
  const nodes = topoNodes.map((name, i) => {
    const baseSize = [44, 32, 32, 32, 26, 26, 26, 26][i];
    return { name, symbolSize: i === idx ? baseSize * 1.5 : baseSize };
  });
  topoInstance.value.setOption({ series: [{ data: nodes }] }, false);
}

// 饼图数据动态更新
function animatePie() {
  if (!pieInstance.value || pieInstance.value.isDisposed()) return;
  pieInstance.value.setOption({
    series: [{
      data: [
        { value: Math.round(55 + rng() * 20), name: 'SSD 热点', itemStyle: { color: '#0d4f6b' } },
        { value: Math.round(20 + rng() * 15), name: 'HDD 温备', itemStyle: { color: '#1d5c3a' } },
        { value: Math.round(8 + rng() * 8),  name: '冷归档', itemStyle: { color: '#5c1d4a' } }
      ]
    }]
  }, false);
}

const handleResize = () => {
  topoInstance.value?.resize();
  pieInstance.value?.resize();
};

onMounted(async () => {
  updateTime();
  clockTimer = setInterval(updateTime, 1000);

  // 初始填充少量历史数据让图表有基准线
  for (let i = 0; i < 30; i++) fetchMetrics();

  // 读取配置中的看板刷新间隔
  let pollMs = 1500;
  try {
    const res = await axios.get('http://127.0.0.1:5000/api/config/params')
    const sec = Number(res.data?.dashboard_refresh_sec) || 0
    if (sec > 0) pollMs = sec * 1000;
  } catch { /* default */ }

  pollTimer = setInterval(fetchMetrics, pollMs);
  // 拓扑节点每2秒随机闪烁
  topoFlashTimer = setInterval(animateTopo, 2000);
  // 饼图每3秒更新一次
  setInterval(animatePie, 3000);

  setTimeout(() => {
    initTopoChart();
    initPieChart();
  }, 200);
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  clearInterval(pollTimer);
  clearInterval(clockTimer);
  clearInterval(topoFlashTimer);
  window.removeEventListener('resize', handleResize);
  topoInstance.value?.dispose();
  pieInstance.value?.dispose();
});
</script>

<template>
  <div class="cyber-monitor-page">
    <header class="header">
      <div class="header-left">
        <button class="cyber-btn" @click="router.push('/')">
          <span class="btn-text">[ 退出 ] BACK</span>
        </button>
      </div>

      <div class="header-center">
        <h1 class="main-title">轻言OPS 可视化监控大屏</h1>
      </div>

      <div class="header-right">
        <div class="time-display">{{ currentTime }}</div>
      </div>
    </header>

    <main class="main-grid">
      <aside class="side-panel left-panel">
        <div class="cyber-card memory-card">
          <div class="card-corner top-left"></div>
          <div class="card-corner bottom-right"></div>
          <h3 class="card-title">数据分析一：内存资源调度</h3>
          <div class="chart-container progress-list">
            <div class="memory-summary">
              <div class="mem-total">
                <div class="mem-val-row">
                  <span class="mem-total-num">{{ memData.length ? Math.round(memData[memData.length - 1]) : 0 }}</span>
                  <span class="mem-unit">%</span>
                </div>
                <span class="mem-total-label">当前占用</span>
              </div>
              <div class="mem-avg">
                <div class="mem-val-row">
                  <span class="mem-avg-num">{{ memData.length ? Math.round(memData.reduce((a,b) => a+b, 0) / memData.length) : 0 }}</span>
                  <span class="mem-unit">%</span>
                </div>
                <span class="mem-avg-label">平均负载</span>
              </div>
            </div>
            <div class="mem-divider"></div>
            <div class="progress-item" v-for="(val, idx) in nodeMemData" :key="idx">
              <div class="progress-label">
                <span class="node-name">节点 0{{ idx + 1 }}</span>
                <span class="node-value" :class="val > 85 ? 'danger' : val > 70 ? 'warn' : 'safe'">{{ val.toFixed(1) }}%</span>
              </div>
              <div class="progress-track">
                <div class="progress-bar"
                  :style="{
                    width: val + '%',
                    background: val > 85
                      ? 'linear-gradient(90deg, #ff3355, #ff0055)'
                      : val > 70
                      ? 'linear-gradient(90deg, #ff8800, #ffaa00)'
                      : 'linear-gradient(90deg, #0055ff, #00f3ff)'
                  }">
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="cyber-card">
          <h3 class="card-title">数据分析二：网络吞吐雷达</h3>
          <div class="chart-container radar-container">
             <MonitorChart
              :timestamps="timeData"
              :seriesData="[
                { name: '下行 (In)', data: netInData, color: '#00f3ff' },
                { name: '上行 (Out)', data: netOutData, color: '#0055ff' }
              ]"
            />
          </div>
        </div>

        <div class="cyber-card">
          <h3 class="card-title">人员结构与权限链路</h3>
          <div class="chart-container" ref="topoChartRef"></div>
        </div>
      </aside>

      <section class="center-panel">
        <div class="top-indicators">
          <div class="indicator-card">
            <span class="label">实时事件拦截</span>
            <span class="value num-scroll">{{ eventIntercept.toLocaleString() }}</span>
          </div>
          <div class="indicator-card active-indicator">
            <span class="label">活跃监控节点</span>
            <span class="value num-scroll">{{ activeNodes.toLocaleString() }}</span>
          </div>
          <div class="indicator-card">
            <span class="label">工单办理数量</span>
            <span class="value num-scroll">{{ ticketDone.toLocaleString() }}</span>
          </div>
        </div>

        <div class="hologram-map">
          <CenterHologramGlobe />
        </div>

        <div class="bottom-indicators">
          <div class="marquee-border">
            <div class="bottom-data-content">
              系统状态: <span class="status-ok">运行良好 (ALL SYSTEMS GO)</span> |
              当前 CPU 负载: <span class="num-scroll">{{ cpuData.length ? cpuData[cpuData.length - 1].toFixed(1) : 0 }}%</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="side-panel right-panel">
        <div class="cyber-card">
          <h3 class="card-title">数据分析三：CPU 动态算力池</h3>
          <div class="chart-container bar-container">
             <MonitorChart
              :timestamps="timeData"
              :seriesData="[{ name: 'CPU 负载', data: cpuData, color: '#00f3ff' }]"
            />
          </div>
        </div>

        <div class="cyber-card">
          <h3 class="card-title">数据分析四：磁盘 I/O 矩阵</h3>
          <div class="chart-container ring-container">
            <MonitorChart
              :timestamps="timeData"
              :seriesData="[
                { name: '读取 (R)', data: diskReadData, color: '#ff00aa' },
                { name: '写入 (W)', data: diskWriteData, color: '#00f3ff' }
              ]"
            />
          </div>
        </div>

        <div class="cyber-card">
          <div class="card-corner top-right"></div>
          <div class="card-corner bottom-left"></div>
          <h3 class="card-title">数据中心：存储分布占比</h3>
          <div class="chart-container" ref="pieChartRef"></div>
        </div>
      </aside>
    </main>
  </div>
</template>

<style scoped>
:root {
  --cyan: #00f3ff;
  --blue: #0055ff;
  --dark-bg: #010409;
}

* {
  box-sizing: border-box;
}

.cyber-monitor-page {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 9999;
  zoom: calc(1 / 0.85);
  background-color: #010409;
  background-image:
    linear-gradient(rgba(0, 243, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 243, 255, 0.03) 1px, transparent 1px);
  background-size: 30px 30px;
  color: #fff;
  font-family: 'Rajdhani', 'Microsoft YaHei', sans-serif;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 60px;
  padding: 0 20px;
  background: url('data:image/svg+xml;utf8,<svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><path d="M0 58 L300 58 L330 30 Lcalc(100% - 330) 30 Lcalc(100% - 300) 58 L100% 58" fill="none" stroke="rgba(0, 243, 255, 0.4)" stroke-width="2"/></svg>') no-repeat center bottom;
  position: relative;
  flex-shrink: 0;
  margin-bottom: 10px;
}

.main-title {
  font-size: 28px;
  font-weight: 700;
  color: #00f3ff;
  text-shadow: 0 2px 8px rgba(0, 243, 255, 0.4);
  letter-spacing: 3px;
  margin: 0;
  text-align: center;
}

.header-left, .header-right {
  width: 30%;
  display: flex;
  align-items: center;
}
.header-right {
  justify-content: flex-end;
}

.time-display {
  font-size: 16px;
  color: #00f3ff;
  font-family: monospace;
}

.cyber-btn {
  background: transparent;
  border: 1px solid #00f3ff;
  color: #00f3ff;
  padding: 4px 12px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  box-shadow: 0 0 5px rgba(0, 243, 255, 0.2) inset;
  transition: 0.3s;
  font-size: 12px;
}
.cyber-btn:hover {
  background: rgba(0, 243, 255, 0.2);
}

.main-grid {
  display: grid;
  grid-template-columns: 25% 50% 25%;
  flex: 1;
  min-height: 0;
  padding: 10px 20px 20px 20px;
  gap: 15px;
}

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 15px;
  height: 100%;
}

.cyber-card {
  flex: 1;
  background: rgba(2, 18, 40, 0.65);
  border: 1px solid rgba(0, 243, 255, 0.3);
  position: relative;
  padding: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 0 10px rgba(0, 20, 50, 0.5) inset;
  min-height: 0;
}

.card-title {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #fff;
  border-left: 3px solid #00f3ff;
  padding-left: 8px;
}

.chart-container {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-height: 0;
}

.card-corner {
  position: absolute;
  width: 10px;
  height: 10px;
  border: 2px solid #00f3ff;
}
.top-left { top: 0; left: 0; border-right: none; border-bottom: none; }
.bottom-right { bottom: 0; right: 0; border-left: none; border-top: none; }
.top-right { top: 0; right: 0; border-left: none; border-bottom: none; }
.bottom-left { bottom: 0; left: 0; border-right: none; border-top: none; }

.memory-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }

.memory-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.mem-total, .mem-avg {
  flex: 1;
  background: rgba(0, 243, 255, 0.05);
  border: 1px solid rgba(0, 243, 255, 0.15);
  border-radius: 8px;
  padding: 6px 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.mem-val-row {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.mem-total-num, .mem-avg-num {
  font-size: 22px;
  font-weight: 700;
  color: #00f3ff;
  line-height: 1;
}

.mem-unit {
  font-size: 14px;
  color: #88bbff;
  font-weight: 500;
}

.mem-total-label, .mem-avg-label {
  font-size: 11px;
  color: #6a8aaa;
}

.mem-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0, 243, 255, 0.2), transparent);
  margin: 0 0 6px 0;
  flex-shrink: 0;
}

.progress-list { display: flex; flex-direction: column; justify-content: space-between; gap: 2px; flex: 1; min-height: 0; padding-bottom: 4px; }

.progress-item { margin-bottom: 0; }
.progress-label { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 3px; }

.node-name { color: #88bbdd; font-weight: 500; }
.node-value { font-weight: 700; font-family: monospace; }
.node-value.safe { color: #00f3ff; }
.node-value.warn { color: #ffaa00; }
.node-value.danger { color: #ff3355; text-shadow: 0 0 6px rgba(255, 51, 85, 0.5); }

.progress-track { width: 100%; height: 4px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden; }
.progress-bar { height: 100%; border-radius: 3px; transition: width 0.8s ease, background 0.5s ease; box-shadow: 0 0 6px rgba(0, 243, 255, 0.3); }

.center-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.top-indicators {
  display: flex;
  justify-content: space-between;
  gap: 15px;
  height: 80px;
  flex-shrink: 0;
}
.indicator-card {
  flex: 1;
  background: linear-gradient(180deg, rgba(0,85,255,0.1) 0%, rgba(0,243,255,0.05) 100%);
  border: 1px solid rgba(0,243,255,0.3);
  padding: 10px;
  text-align: center;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.indicator-card.active-indicator {
  border-color: #00f3ff;
  box-shadow: 0 0 10px rgba(0,243,255,0.2) inset;
}
.indicator-card .label { display: block; font-size: 13px; color: #88bbff; margin-bottom: 2px;}
.indicator-card .value { display: block; font-size: 24px; font-weight: bold; color: #fff; font-family: monospace;}

.hologram-map {
  flex: 1;
  margin: 15px 0;
  position: relative;
  background: radial-gradient(circle at center, rgba(0,85,255,0.1) 0%, transparent 60%);
  border: 1px solid rgba(0, 243, 255, 0.1);
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 0;
}

.bottom-indicators {
  height: 40px;
  flex-shrink: 0;
  background: rgba(2, 18, 40, 0.65);
  border: 1px solid rgba(0, 243, 255, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
}
.bottom-data-content {
  color: #fff;
  font-size: 14px;
}
.status-ok { color: #00ff88; text-shadow: 0 0 5px #00ff88; }
</style>
