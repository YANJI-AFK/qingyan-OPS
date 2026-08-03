<template>
  <div ref="chartRef" class="chart-container"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import * as echarts from 'echarts';

interface SeriesItem {
  name: string;
  data: number[];
  color: string;
}

const props = defineProps<{
  timestamps: string[];
  seriesData: SeriesItem[];
}>();

const chartRef = ref<HTMLDivElement | null>(null);
let chartInstance: echarts.ECharts | null = null;
let userChangedZoom = false; // 用户是否手动拖动了波动条

const buildOption = () => {
  const total = props.timestamps.length;
  const VISIBLE_WINDOW = 20;
  let startPct = 0, endPct = 100;
  if (total > VISIBLE_WINDOW) {
    startPct = Math.round((total - VISIBLE_WINDOW) / total * 100);
    endPct = 100;
  }
  return {
    animationDuration: 600,
    animationEasing: 'linear',
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(2, 18, 40, 0.95)',
      borderColor: '#00f3ff',
      textStyle: { color: '#fff', fontSize: 12 }
    },
    legend: {
      top: '0%',
      right: '4%',
      icon: 'circle',
      textStyle: { color: '#88bbff', fontSize: 11 }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '8%',  // 给波动条留空间
      top: '18%',
      containLabel: true
    },
    dataZoom: [
      {
        type: 'slider',
        start: startPct,
        end: endPct,
        height: 8,
        bottom: 0,
        borderColor: 'transparent',
        backgroundColor: 'transparent',
        fillerColor: 'rgba(0,243,255,0.04)',
        handleStyle: { color: 'rgba(0,243,255,0.3)', borderColor: 'transparent' },
        textStyle: { color: 'transparent', fontSize: 0 },
        showDetail: false,
        showDataShadow: false,
        labelFormatter: () => '',
        brushSelect: false,
        // 用户操作时标记
        on: {
          dataZoom: () => { userChangedZoom = true; }
        }
      }
    ],
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.timestamps,
      axisLine: { lineStyle: { color: 'rgba(0,243,255,0.3)' } },
      axisLabel: { color: '#88bbff', fontSize: 10 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { type: 'dashed', color: 'rgba(0,243,255,0.1)' } },
      axisLabel: { color: '#88bbff', fontSize: 10 }
    },
    series: props.seriesData.map(item => ({
      name: item.name,
      type: 'line',
      smooth: true,
      showSymbol: false,
      animationDuration: 600,
      animationEasing: 'linear',
      itemStyle: { color: item.color },
      lineStyle: { width: 2 },
      areaStyle: {
        opacity: 0.15,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: item.color },
          { offset: 1, color: 'rgba(0, 0, 0, 0)' }
        ])
      },
      data: item.data
    }))
  };
};

const initChart = () => {
  if (!chartRef.value) return;
  chartInstance = echarts.init(chartRef.value);
  chartInstance.setOption(buildOption());
};

// 数据变化时：只更新数据，不覆盖用户拖动的波动条位置
watch(
  () => [props.timestamps, props.seriesData],
  () => {
    if (!chartInstance || chartInstance.isDisposed()) return;

    const option: any = {
      xAxis: { data: props.timestamps },
      series: props.seriesData.map(item => ({
        name: item.name,
        data: item.data
      }))
    };

    // 只有用户没手动拖过 且 数据增长接近右边界时，才自动推进
    if (!userChangedZoom) {
      const total = props.timestamps.length;
      const VISIBLE_WINDOW = 20;
      if (total > VISIBLE_WINDOW) {
        const startPct = Math.round((total - VISIBLE_WINDOW) / total * 100);
        option.dataZoom = [{ start: startPct, end: 100 }];
      }
    }

    chartInstance.setOption(option, { notMerge: false });
  },
  { deep: true }
);

const handleResize = () => chartInstance?.resize();

onMounted(() => {
  initChart();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  chartInstance?.dispose();
});
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 100%;
  min-height: 150px;
}
</style>
