<script setup lang="ts">
import { ref, onMounted, onUnmounted, shallowRef, nextTick } from 'vue';
import * as echarts from 'echarts';
import 'echarts-gl';

const chartRef = ref<HTMLElement | null>(null);
const chartInstance = shallowRef<echarts.ECharts | null>(null);
let fullscreenHandler: (() => void) | null = null;

const DARK_BG = '#010409';

const createTrajectoryData = () => {
  const targetCoords = [116.46, 39.92];
  const sources = [
    { coords: [-74.00, 40.71], value: 100 },
    { coords: [-0.12, 51.50], value: 50 },
    { coords: [37.61, 55.75], value: 80 },
    { coords: [151.20, -33.86], value: 40 },
    { coords: [-118.24, 34.05], value: 90 },
  ];
  return sources.map(item => ({
    coords: [item.coords, targetCoords],
    value: item.value
  }));
};

// Canvas 兜底：全息网格纹理（100% 离线可用）
const createGridFallbackTexture = () => {
  const canvas = document.createElement('canvas');
  canvas.width = 1024; canvas.height = 512;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = DARK_BG; ctx.fillRect(0, 0, 1024, 512);
  ctx.strokeStyle = 'rgba(0, 200, 255, 0.12)'; ctx.lineWidth = 1;
  for (let i = 0; i <= 1024; i += 32) { ctx.beginPath(); ctx.moveTo(i,0); ctx.lineTo(i,512); ctx.stroke(); }
  for (let j = 0; j <= 512; j += 32) { ctx.beginPath(); ctx.moveTo(0,j); ctx.lineTo(1024,j); ctx.stroke(); }
  return canvas;
};

// 核心：混合贴图 — 把真实世界地图叠到 Canvas 网格上，染成半透明淡蓝色
const loadRealisticTexture = (fallbackCanvas: HTMLCanvasElement): HTMLCanvasElement => {
  const worldImg = new Image();
  worldImg.crossOrigin = 'anonymous';
  worldImg.src = '/world_map.jpg';

  worldImg.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = 1024; canvas.height = 512;
    const ctx = canvas.getContext('2d')!;

    ctx.drawImage(fallbackCanvas, 0, 0);
    ctx.globalAlpha = 0.38;
    ctx.drawImage(worldImg, 0, 0, 1024, 512);
    ctx.globalAlpha = 1.0;
    ctx.fillStyle = 'rgba(0, 180, 240, 0.06)';
    ctx.fillRect(0, 0, 1024, 512);

    if (chartInstance.value && !chartInstance.value.isDisposed()) {
      chartInstance.value.setOption({
        globe: { baseTexture: canvas }
      });
    }
  };

  worldImg.onerror = () => {
    console.warn('[Globe] 地图贴图加载失败，使用纯网格模式');
  };

  return fallbackCanvas;
};

const buildGlobeOption = (texture: HTMLCanvasElement) => ({
  backgroundColor: DARK_BG,
  globe: {
    baseTexture: texture,
    heightTexture: '',
    shading: 'color',
    globeOuterColor: DARK_BG,
    atmosphere: {
      show: true,
      offset: 5,
      color: '#00b8e6',
      glowPower: 4,
      innerGlowPower: 2
    },
    viewControl: {
      autoRotate: true,
      autoRotateSpeed: 4,
      targetCoord: [116.46, 39.92],
      zoomSensitivity: 0,
      distance: 145
    }
  },
  series: [
    {
      type: 'lines3D',
      coordinateSystem: 'globe',
      blendMode: 'lighter',
      effect: { show: true, trailWidth: 3, trailLength: 0.5, trailOpacity: 1, trailColor: '#00f3ff' },
      lineStyle: { width: 1.5, color: 'rgba(0, 243, 255, 0.2)', opacity: 0.2 },
      data: createTrajectoryData()
    },
    {
      type: 'scatter3D',
      coordinateSystem: 'globe',
      symbolSize: 8,
      itemStyle: { color: '#ff0055', opacity: 1, shadowBlur: 20, shadowColor: '#ff0055' },
      data: [[-74.00,40.71],[-0.12,51.50],[37.61,55.75],[151.20,-33.86],[-118.24,34.05]]
    },
    {
      type: 'scatter3D',
      coordinateSystem: 'globe',
      symbolSize: 20,
      itemStyle: { color: '#ffffff', opacity: 1, shadowBlur: 30, shadowColor: '#00f3ff' },
      data: [[116.46, 39.92]]
    }
  ]
});

const destroyGlobe = () => {
  try { chartInstance.value?.dispose(); } catch { /* ignore */ }
  chartInstance.value = null;
};

const initGlobe = () => {
  if (!chartRef.value) return;
  // 容器尺寸为 0 时跳过
  const rect = chartRef.value.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return;

  destroyGlobe();
  chartInstance.value = echarts.init(chartRef.value);

  const fallbackTexture = createGridFallbackTexture();
  const texture = loadRealisticTexture(fallbackTexture);

  chartInstance.value.setOption(buildGlobeOption(texture));
};

// 全屏切换时重建图表（WebGL 上下文可能在 resize 中丢失）
const onFullscreenChange = () => {
  nextTick(() => {
    setTimeout(() => initGlobe(), 200);
  });
};

const handleResize = () => {
  if (chartInstance.value && !chartInstance.value.isDisposed()) {
    chartInstance.value.resize();
  }
};

onMounted(() => {
  // 延迟初始化确保 DOM 已完成布局
  setTimeout(() => initGlobe(), 300);
  window.addEventListener('resize', handleResize);
  fullscreenHandler = onFullscreenChange;
  document.addEventListener('fullscreenchange', fullscreenHandler);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  if (fullscreenHandler) document.removeEventListener('fullscreenchange', fullscreenHandler);
  destroyGlobe();
});
</script>

<template>
  <div class="globe-wrapper" ref="chartRef"></div>
</template>

<style scoped>
.globe-wrapper {
  width: 100%;
  height: 100%;
  min-height: 400px;
}
</style>
