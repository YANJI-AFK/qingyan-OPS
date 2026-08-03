<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'

// ========== 路由 ==========
const router = useRouter()
const route = useRoute()
const currentRoute = computed(() => route.path)
function goTo(path: string) {
  router.push(path)
}

// ========== 全屏切换 ==========
const isFullscreen = ref(false)
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}
document.addEventListener('fullscreenchange', () => {
  isFullscreen.value = !!document.fullscreenElement
})

// ========== 通知 ==========
const notificationCount = ref(3)

// ========== 夜间模式 ==========
const isDarkMode = ref(localStorage.getItem('litevox-dark') === '1')
function toggleDarkMode() {
  isDarkMode.value = !isDarkMode.value
  localStorage.setItem('litevox-dark', isDarkMode.value ? '1' : '0')
  document.documentElement.classList.toggle('dark', isDarkMode.value)
}
// 初始化：页面加载时同步主题
onMounted(() => {
  document.documentElement.classList.toggle('dark', isDarkMode.value)
  loadVoices()
})

// ========== 监听首页"语音助手"快捷入口 ==========
function onFocusAssistant() {
  if (isMinimized.value) isMinimized.value = false
  const el = document.querySelector('.floating-window') as HTMLElement | null
  if (el) {
    el.style.transition = 'box-shadow 0.3s'
    el.style.boxShadow = '0 0 0 3px #1890ff, 0 6px 16px -8px rgba(0,0,0,0.08)'
    setTimeout(() => { el.style.boxShadow = '' }, 1500)
  }
}
onMounted(() => window.addEventListener('focus-assistant', onFocusAssistant))
onUnmounted(() => {
  window.removeEventListener('focus-assistant', onFocusAssistant)
  stopConfirmCountdown()  // 释放倒计时
})

// ========== 持续聆听模式（VAD 自动检测）==========
const continuousMode = ref(false)            // 开关
type VadState = 'idle' | 'listening' | 'speaking' | 'processing'
const vadState = ref<VadState>('idle')       // 当前状态
let audioCtx: AudioContext | null = null
let mediaStream: MediaStream | null = null
let analyser: AnalyserNode | null = null
let vadTimerId: number | null = null
let silenceCounter = 0
let speechFrames = 0
let noiseFloor = 0.01       // 环境底噪基线（动态更新）
let noiseUpdateCounter = 0  // 持续静音帧计数（用于定期重新校准）
let recordingStartTime = 0  // 录音开始时间戳（毫秒）

// VAD 参数（可调节）
const VAD_SENSITIVITY = 2.5        // 阈值 = 噪声基线 × 灵敏度倍数。2.5 更灵敏，适用于大多数环境
const SILENCE_TIMEOUT_MS = 1800    // 静音判定超时（1.8 秒，说一句完整话后快速响应）
const MIN_SPEECH_MS = 300          // 最短有效语音（过滤瞬时噪声）
const MIN_RECORDING_MS = 800       // 最短录音时长（一句话约 0.8~1.5s，不再丢弃短命令）
const NOISE_UPDATE_INTERVAL = 60   // 每 60 帧（3 秒）持续静音时重新校准噪声基线
const VAD_POLL_MS = 50
const SILENCE_MAX = Math.ceil(SILENCE_TIMEOUT_MS / VAD_POLL_MS)
const SPEECH_MIN_FRAMES = Math.ceil(MIN_SPEECH_MS / VAD_POLL_MS)
const RECORDING_MIN_FRAMES = Math.ceil(MIN_RECORDING_MS / VAD_POLL_MS)

// ========== 语音录制 ==========
const isRecording = ref(false)
const lastResult = ref('')
const isMuted = ref(false)
const isMinimized = ref(false)
const realtimeText = ref('')  // 实时转写文字

interface ChatMsg { type: 'user' | 'assistant' | 'realtime'; text: string }
const chatMessages = ref<ChatMsg[]>([])

let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []
let recordingStream: MediaStream | null = null  // 录音专用流（与VAD分析流分开）

// ========== 浏览器实时语音识别（Web Speech API）==========
let speechRecognition: any = null
let speechRecognitionRunning = false

function initSpeechRecognition() {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    console.warn('[实时转写] 浏览器不支持 SpeechRecognition API')
    return null
  }
  const recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = true   // 启用中间结果（边说边显示）
  recognition.continuous = true       // 持续识别
  recognition.maxAlternatives = 1

  recognition.onresult = (event: any) => {
    let interim = ''
    let final = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      if (result.isFinal) {
        final += result[0].transcript
      } else {
        interim += result[0].transcript
      }
    }
    // 实时更新显示
    realtimeText.value = final + interim
  }

  recognition.onerror = (event: any) => {
    if (event.error === 'no-speech') {
      // 静默期，正常情况，忽略
      return
    }
    console.warn('[实时转写] 错误:', event.error)
  }

  recognition.onend = () => {
    speechRecognitionRunning = false
  }

  return recognition
}

function startRealtimeTranscription() {
  if (!speechRecognition) {
    speechRecognition = initSpeechRecognition()
  }
  if (!speechRecognition) return

  try {
    speechRecognition.start()
    speechRecognitionRunning = true
    realtimeText.value = ''
    console.log('[实时转写] 🎙️ 已启动')
  } catch (e) {
    console.warn('[实时转写] 启动失败:', e)
  }
}

function stopRealtimeTranscription(): string {
  const finalText = realtimeText.value
  if (speechRecognition && speechRecognitionRunning) {
    try {
      speechRecognition.stop()
    } catch (e) { /* ignore */ }
  }
  speechRecognitionRunning = false
  realtimeText.value = ''
  return finalText
}

function addMessage(type: 'user' | 'assistant', text: string) {
  chatMessages.value.push({ type, text })
  if (chatMessages.value.length > 10) chatMessages.value.shift()
  setTimeout(() => {
    const box = document.querySelector('.chat-area')
    if (box) box.scrollTop = box.scrollHeight
  }, 50)
}

function clearChat() {
  chatMessages.value = []
}

function toggleMute() {
  isMuted.value = !isMuted.value
  // 开启静音时，立即停止当前正在播放的 TTS
  if (isMuted.value && ttsState.value !== 'idle') {
    stopTTS()
  }
}

function toggleMinimize() {
  isMinimized.value = !isMinimized.value
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
    audioChunks = []

    // 🔥 启动浏览器实时语音识别（边说边显示）
    startRealtimeTranscription()

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      if (audioChunks.length === 0) return

      // 🔥 获取实时转写的最终文本（先于后端 FunASR 显示在屏幕上）
      const realtimeResult = stopRealtimeTranscription()

      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' })
      console.log(`[录音] 录制完成, ${(audioBlob.size / 1024).toFixed(1)} KB`)

      const fd = new FormData()
      fd.append('file', audioBlob, 'recording.wav')

      try {
        const res = await axios.post('http://127.0.0.1:5000/api/transcribe', fd, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        const recognized = res.data.text || ''
        if (!recognized) {
          // 后端 FunASR 未识别到，回退用浏览器转写结果
          if (realtimeResult) {
            lastResult.value = realtimeResult
            addMessage('user', realtimeResult)
            await sendToChat(realtimeResult)
          } else {
            lastResult.value = '(未识别)'
          }
          return
        }
        lastResult.value = recognized
        addMessage('user', recognized)

        await sendToChat(recognized)
      } catch (err) {
        console.error('[录音] 失败:', err)
        // 降级：用浏览器转写结果
        if (realtimeResult) {
          lastResult.value = realtimeResult
          addMessage('user', realtimeResult)
          await sendToChat(realtimeResult)
        } else {
          lastResult.value = '⚠️ 识别失败'
        }
      }
    }

    mediaRecorder.start()
    isRecording.value = true
    console.log('[录音] 🎙️ 开始录制（含实时转写）')
  } catch (err) {
    console.error('[录音] 启动失败:', err)
    stopRealtimeTranscription()
    alert('无法访问麦克风, 请检查权限')
  }
}

// 将识别文本发送到聊天后端
async function sendToChat(recognized: string) {
  try {
    const chatRes = await axios.post('http://127.0.0.1:5000/chat', { text: recognized })
    const {
      reply_text: reply,
      action,
      target,
      sync_filters: syncFilters,
      pre_tts: preTts,
      refresh_schedule: refreshSchedule,
    } = chatRes.data

    if (reply) {
      lastResult.value = reply
      addMessage('assistant', reply)
      if (!isMuted.value) {
        if (preTts) {
          playTTSChain([preTts, reply])
        } else {
          playTTS(reply)
        }
      }
    }

    if (action === 'navigate' && target) {
      router.push(target)
    }
    applySyncFilters(syncFilters)
    if (refreshSchedule) {
      window.dispatchEvent(new CustomEvent('schedule-refresh'))
    }
  } catch (err) {
    console.error('[聊天] 请求失败:', err)
    addMessage('assistant', '抱歉，服务器暂时无法响应，请稍后重试')
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop()
    isRecording.value = false
  }
}

/** 切换录音：点一下开始 → 再点一下识别并停止 */
function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else {
    startRecording()
  }
}

// ========== 音量控制 ==========
const volume = ref(parseFloat(localStorage.getItem('litevox_volume') ?? '0.8'))
function setVolume(v: number) {
  volume.value = Math.round(v * 100) / 100
  localStorage.setItem('litevox_volume', String(volume.value))
}

// ========== 语速控制 ==========
// 映射：前端 0.5~2.0 倍速 → 后端 SAPI rate -8(很慢) ~ +10(很快)，默认 -4（明显稍慢）
// 公式: rate = round((speed - 1) × 18)，0.5x→-9, 0.85x→-3(实际有效差异), 1.0x→0, 2.0x→+18→卡+10
const speed = ref(parseFloat(localStorage.getItem('litevox_speed') ?? '0.85'))
const ttsRate = computed(() => Math.max(-10, Math.min(10, Math.round((speed.value - 1) * 20))))
function setSpeed(v: number) {
  speed.value = Math.round(v * 100) / 100
  localStorage.setItem('litevox_speed', String(speed.value))
}

// ========== 音色控制 ==========
const availableVoices = ref<{ id: string; name: string; gender: string }[]>([])
const selectedVoice = ref(localStorage.getItem('litevox_voice') || 'sherpa-0')
function setVoice(v: string) {
  selectedVoice.value = v
  localStorage.setItem('litevox_voice', v)
}
// 加载语音列表
async function loadVoices() {
  try {
    const res = await axios.get('http://127.0.0.1:5000/api/tts/voices')
    availableVoices.value = res.data || []
    if (availableVoices.value.length === 0) {
      availableVoices.value = [
        { id: 'default', name: '系统默认', gender: 'male' },
      ]
    }
  } catch {
    availableVoices.value = [{ id: 'default', name: '系统默认', gender: 'male' }]
  }
}

// ========== TTS 播放控制 ==========
type TtsState = 'idle' | 'playing' | 'paused'
const ttsState = ref<TtsState>('idle')
const showTtsSettings = ref(false)
let currentAudio: HTMLAudioElement | null = null
let currentAudioUrl = ''

async function playTTS(text: string) {
  // 先停止当前播放
  stopTTS()
  try {
    const res = await axios.post('http://127.0.0.1:5000/api/tts', {
      text,
      rate: ttsRate.value,
      voice: selectedVoice.value,
    }, { responseType: 'blob' })
    currentAudioUrl = URL.createObjectURL(res.data)
    currentAudio = new Audio(currentAudioUrl)
    currentAudio.volume = volume.value
    currentAudio.onended = () => { cleanupTTS(); URL.revokeObjectURL(currentAudioUrl) }
    currentAudio.onerror = () => { cleanupTTS(); URL.revokeObjectURL(currentAudioUrl) }
    // 等待音频数据真正加载完成再播放，彻底杜绝吞开头字
    await new Promise<void>((resolve) => {
      if (currentAudio!.readyState >= 3) { resolve(); return }
      currentAudio!.addEventListener('loadeddata', () => resolve(), { once: true })
      currentAudio!.load()
    })
    await currentAudio.play()
    ttsState.value = 'playing'
  } catch (err) {
    console.warn('[TTS] 播放失败:', err)
    cleanupTTS()
  }
}

/**
 * 串播两段 TTS（"组合拳"反馈）
 * 需求：操作类意图先播"收到！正在执行 XXX..."，再播真实结果
 * 串行播放：播完前一段才放后一段；任何一段失败都不影响后续
 */
async function playTTSChain(texts: string[]) {
  for (const t of texts) {
    if (!t) continue
    if (isMuted.value) return
    // 等待当前这一段播完再放下一段
    await new Promise<void>((resolve) => {
      try {
        axios.post('http://127.0.0.1:5000/api/tts', {
          text: t,
          rate: ttsRate.value,
          voice: selectedVoice.value,
        }, { responseType: 'blob' })
          .then(res => {
            const url = URL.createObjectURL(res.data)
            const a = new Audio(url)
            a.volume = volume.value
            a.onended = () => { URL.revokeObjectURL(url); resolve() }
            a.onerror = () => { URL.revokeObjectURL(url); resolve() }
            a.play().catch(() => resolve())
          })
          .catch(() => resolve())
      } catch {
        resolve()
      }
    })
  }
}

function pauseTTS() {
  if (currentAudio && ttsState.value === 'playing') {
    currentAudio.pause()
    ttsState.value = 'paused'
  }
}

function resumeTTS() {
  if (currentAudio && ttsState.value === 'paused') {
    currentAudio.play()
    ttsState.value = 'playing'
  }
}

function stopTTS() {
  if (currentAudio) {
    try {
      currentAudio.pause()
      currentAudio.currentTime = 0
    } catch (e) {
      console.warn('[TTS] 停止时出错:', e)
    }
  }
  if (currentAudioUrl) {
    URL.revokeObjectURL(currentAudioUrl)
    currentAudioUrl = ''
  }
  cleanupTTS()
}

function cleanupTTS() {
  currentAudio = null
  ttsState.value = 'idle'
}

// ========== 持续聆听模式 ==========

async function toggleContinuousMode() {
  if (continuousMode.value) {
    stopContinuous()
  } else {
    await startContinuous()
  }
}

async function startContinuous() {
  try {
    continuousMode.value = true
    vadState.value = 'listening'

    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
      }
    })
    audioCtx = new AudioContext()
    const source = audioCtx.createMediaStreamSource(mediaStream)
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 256
    source.connect(analyser)

    console.log('[VAD] 📏 正在校准环境噪声基线...')
    noiseFloor = await calibrateNoiseFloor()
    console.log(`[VAD] ✅ 噪声: ${noiseFloor.toFixed(4)}, 阈值: ${(noiseFloor * VAD_SENSITIVITY).toFixed(4)}`)

    silenceCounter = 0
    speechFrames = 0
    pollVAD()
    console.log('[VAD] 🟢 持续聆听已开启')
  } catch (err) {
    console.error('[VAD] 启动失败:', err)
    continuousMode.value = false
    vadState.value = 'idle'
    alert('无法访问麦克风，请检查权限')
  }
}

function stopContinuous() {
  continuousMode.value = false
  vadState.value = 'idle'
  silenceCounter = 0
  speechFrames = 0
  if (vadTimerId !== null) { cancelAnimationFrame(vadTimerId); vadTimerId = null }
  if (isRecording.value && mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop()
    isRecording.value = false
  }
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null }
  if (recordingStream) { recordingStream.getTracks().forEach(t => t.stop()); recordingStream = null }
  if (audioCtx) { audioCtx.close(); audioCtx = null; analyser = null }
  console.log('[VAD] 🔴 持续聆听已关闭')
}

async function calibrateNoiseFloor(): Promise<number> {
  if (!analyser) return 0.02
  const buffer = new Uint8Array(analyser.frequencyBinCount)
  let total = 0
  const samples = 30
  for (let i = 0; i < samples; i++) {
    analyser.getByteTimeDomainData(buffer)
    let sum = 0
    for (let j = 0; j < buffer.length; j++) {
      const v = (buffer[j]! - 128) / 128
      sum += v * v
    }
    total += Math.sqrt(sum / buffer.length)
    await new Promise(r => setTimeout(r, VAD_POLL_MS))
  }
  return Math.max(total / samples, 0.005)
}

function pollVAD() {
  if (!continuousMode.value || !analyser) return

  const bufferLength = analyser.frequencyBinCount
  const dataArray = new Uint8Array(bufferLength)
  analyser.getByteTimeDomainData(dataArray)

  // --- 计算 RMS 能量 ---
  let sum = 0
  for (let i = 0; i < bufferLength; i++) {
    const v = (dataArray[i]! - 128) / 128
    sum += v * v
  }
  const rms = Math.sqrt(sum / bufferLength)

  // --- 频率分析：判定是否为低频噪声（风扇等） ---
  // 用频谱数据判断：低频段(<500Hz)能量占比 > 80% 时，判定为噪声而非人声
  const freqData = new Uint8Array(analyser.frequencyBinCount)
  analyser.getByteFrequencyData(freqData)
  let lowFreqEnergy = 0
  let totalFreqEnergy = 0
  const lowFreqBins = Math.floor(bufferLength * 0.15) // 约前15%频段对应低频
  for (let i = 0; i < bufferLength; i++) {
    totalFreqEnergy += freqData[i]!
    if (i < lowFreqBins) lowFreqEnergy += freqData[i]!
  }
  const lowFreqRatio = totalFreqEnergy > 0 ? lowFreqEnergy / totalFreqEnergy : 0
  const isNoisePattern = lowFreqRatio > 0.9 && rms < noiseFloor * 2.5

  // --- 动态阈值 ---
  const threshold = noiseFloor * VAD_SENSITIVITY

  if (rms > threshold && !isNoisePattern) {
    // === 检测到语音 ===
    silenceCounter = 0
    noiseUpdateCounter = 0
    speechFrames++

    // 🔥 修复1：第二帧即开始录音（100ms 延迟，不再丢开头字）
    if (vadState.value === 'listening' && speechFrames === 2) {
      handleSpeechStart()
    }
  } else {
    // === 静音或噪声 ===
    speechFrames = 0

    if (vadState.value === 'speaking') {
      silenceCounter++
      const recordingFrames = speechFrames + silenceCounter
      if (silenceCounter >= SILENCE_MAX && recordingFrames >= RECORDING_MIN_FRAMES) {
        // 录音时长不够 → 丢弃（用户只说了半句话又被中断）
        if (Date.now() - recordingStartTime < MIN_RECORDING_MS) {
          console.log('[VAD] ⏭️ 录音时长不足，丢弃')
          abortRecording()
        } else {
          handleSpeechEnd()
        }
      }
    } else if (vadState.value === 'listening') {
      // 🔥 修复3：静音期间动态更新噪声基线（每3秒一次）
      noiseUpdateCounter++
      if (noiseUpdateCounter >= NOISE_UPDATE_INTERVAL) {
        noiseUpdateCounter = 0
        // 用最近0.5秒的采样做滑动平均
        noiseFloor = noiseFloor * 0.7 + rms * 0.3
        if (noiseFloor < 0.002) noiseFloor = 0.002
        if (noiseFloor > 0.2) noiseFloor = 0.2
      }
    }
  }

  vadTimerId = requestAnimationFrame(pollVAD)
}

async function handleSpeechStart() {
  if (vadState.value !== 'listening') return
  vadState.value = 'speaking'
  speechFrames = 0
  audioChunks = []
  recordingStartTime = Date.now()  // 记录开始时间

  // ⚠️ 获取独立的麦克风流用于录音，不与 VAD 分析共享流
  // 避免浏览器将音频经 AudioContext 路由后 MediaRecorder 收不到数据
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } })
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus' : 'audio/webm'
    const recorder = new MediaRecorder(recordingStream, { mimeType: mime })
    recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data) }
    recorder.onstop = () => {
      // 释放录音专用流
      if (recordingStream) {
        recordingStream.getTracks().forEach(t => t.stop())
        recordingStream = null
      }
      processAudioBlob()
    }
    recorder.start()
    mediaRecorder = recorder
    isRecording.value = true
    console.log('[VAD] 🎙️ 检测到有效语音')
  } catch (err) {
    console.error('[VAD] 获取录音流失败:', err)
    resumeListening()
  }
}

function abortRecording() {
  // 丢弃当前录音：停止但不触发 processAudioBlob
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.onstop = null  // 阻止 processAudioBlob 被调用
    mediaRecorder.stop()
    isRecording.value = false
  }
  // 释放录音专用流
  if (recordingStream) {
    recordingStream.getTracks().forEach(t => t.stop())
    recordingStream = null
  }
  audioChunks = []
  resumeListening()
}

function handleSpeechEnd() {
  vadState.value = 'processing'
  isRecording.value = false
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop()
  }
  console.log('[VAD] ⏸️ 静音检测，处理中...')
}

async function processAudioBlob() {
  if (audioChunks.length === 0) {
    console.log('[VAD] ⚠️ audioChunks 为空，未捕获到录音数据（可能是共享流问题）')
    resumeListening()
    return
  }

  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' })
  const duration = ((Date.now() - recordingStartTime) / 1000).toFixed(1)
  console.log(`[VAD] 录制完成, ${(audioBlob.size / 1024).toFixed(1)} KB, 时长 ${duration}s, chunks: ${audioChunks.length}`)

  const fd = new FormData()
  fd.append('file', audioBlob, 'recording.wav')

  try {
    const res = await axios.post('http://127.0.0.1:5000/api/transcribe', fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    const recognized = res.data.text || ''
    console.log(`[VAD] ASR 返回: "${recognized}" (text=${JSON.stringify(res.data.text)})`)
    if (!recognized) {
      console.log('[VAD] ⚠️ ASR 返回空文本')
      addMessage('assistant', '(未听清，请再说一遍)')
      resumeListening()
      return
    }
    lastResult.value = recognized
    addMessage('user', recognized)

    const chatRes = await axios.post('http://127.0.0.1:5000/chat', { text: recognized })
    console.log('[VAD] Chat 返回:', JSON.stringify(chatRes.data).slice(0, 200))
    const {
      reply_text: reply,
      action,
      target,
      need_confirmation: needConfirm,
      pending_timeout_sec: pendingTimeout,
      sync_filters: syncFilters,
      pre_tts: preTts,
      refresh_schedule: refreshSchedule,
    } = chatRes.data

    if (reply) {
      lastResult.value = reply
      addMessage('assistant', reply)
      // 操作类意图的"组合拳"：先播 pre_tts（收到！正在执行...），再播真实结果
      if (!isMuted.value) {
        if (preTts) {
          playTTSChain([preTts, reply])
        } else {
          playTTS(reply)
        }
      }
    }
    if (action === 'navigate' && target) { router.push(target) }

    // 工单多条件搜索 → 联动同步前端筛选器
    applySyncFilters(syncFilters)
    if (refreshSchedule) {
      window.dispatchEvent(new CustomEvent('schedule-refresh'))
    }

    // 二次确认：启动 / 停止右上角角标倒计时
    if (needConfirm && pendingTimeout && pendingTimeout > 0) {
      startConfirmCountdown(pendingTimeout)
    } else {
      stopConfirmCountdown()
    }
  } catch (err) {
    console.error('[VAD] ❌ 识别/聊天请求失败:', (err as any).message || err)
    // 尝试打印更详细的信息
    if ((err as any).response) {
      console.error('[VAD] 响应状态:', (err as any).response.status, (err as any).response.data)
    }
    addMessage('assistant', '⚠️ 抱歉，识别出错了')
  }
  resumeListening()
}

// ========== 二次确认倒计时（浮窗右上角角标）==========
const pendingCountdown = ref(0)        // 剩余秒数（0 = 不显示）
const pendingTotal = ref(0)            // 总秒数（用于进度环）
let pendingTimerId: number | null = null

function startConfirmCountdown(totalSec: number) {
  stopConfirmCountdown()  // 防止重叠
  pendingTotal.value = totalSec
  pendingCountdown.value = totalSec
  pendingTimerId = window.setInterval(() => {
    pendingCountdown.value = Math.max(0, pendingCountdown.value - 1)
    if (pendingCountdown.value <= 0) {
      stopConfirmCountdown()
    }
  }, 1000)
}

function stopConfirmCountdown() {
  if (pendingTimerId !== null) {
    clearInterval(pendingTimerId)
    pendingTimerId = null
  }
  pendingCountdown.value = 0
  pendingTotal.value = 0
}

// ========== 工单搜索联动（语音搜索 → 前端筛选器）==========
// 当后端返回 sync_filters 时，把它写到 localStorage + 派发 window 事件。
// TicketsPage.vue 等任何页面的筛选下拉框挂监听器即可同步刷新。
function applySyncFilters(filters: Record<string, any> | null | undefined) {
  if (!filters || typeof filters !== 'object' || Object.keys(filters).length === 0) return
  try {
    localStorage.setItem('ticketSearchSync', JSON.stringify({
      filters,
      ts: Date.now(),
    }))
    // 派发 CustomEvent，让同窗口的组件实时收到
    window.dispatchEvent(new CustomEvent('ticket-search-sync', { detail: { filters } }))
    console.log('[sync] 工单筛选器已同步:', filters)
  } catch (e) {
    console.warn('[sync] 同步失败:', e)
  }
}

function resumeListening() {
  audioChunks = []
  silenceCounter = 0
  speechFrames = 0
  if (continuousMode.value) {
    vadState.value = 'listening'
  }
}
</script>

<template>
  <div id="app">
    <!-- 真实业务系统风格的顶栏 -->
    <nav class="topnav">
      <div class="topnav-left">
        <div class="brand-area" @click="goTo('/')">
          <svg class="brand-logo" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="6" fill="#1890ff"/>
            <path d="M9 21V11l7 5.5L9 21z" fill="#fff" opacity="0.9"/>
            <path d="M16 16.5v-5.5l7 5.5-7 5.5v-5.5z" fill="#fff" opacity="0.6"/>
          </svg>
          <span class="brand-text">轻言OPS</span>
        </div>
        <div class="nav-links">
          <button class="nav-item" :class="{ active: currentRoute === '/' }" @click="goTo('/')">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
            首页
          </button>
          <button class="nav-item" :class="{ active: currentRoute === '/monitor' }" @click="goTo('/monitor')">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/></svg>
            监控大盘
          </button>
          <button class="nav-item" :class="{ active: currentRoute.startsWith('/tickets') }" @click="goTo('/tickets')">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm-1 7V3.5L18.5 9H13zM6 20V4h5v7h7v9H6z"/></svg>
            工单管理
          </button>
          <button class="nav-item" :class="{ active: currentRoute.startsWith('/staff') }" @click="goTo('/staff')">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg>
            人员管理
          </button>
        </div>
      </div>
      
      <div class="topnav-right">
        <button class="topnav-icon-btn" title="全屏" @click="toggleFullscreen">
          <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18">
            <path d="M5 5h5v2H7v3H5V5zm9 0h5v5h-2V7h-3V5zm5 14h-5v-2h3v-3h2v5zM5 19v-5h2v3h3v2H5z"/>
          </svg>
        </button>
        <button class="topnav-icon-btn" :title="isDarkMode ? '切换日间模式' : '切换夜间模式'" @click="toggleDarkMode">
          <!-- 月亮图标（夜间模式） -->
          <svg v-if="!isDarkMode" viewBox="0 0 24 24" fill="currentColor" width="18" height="18">
            <path d="M12.43 2.3a9.917 9.917 0 00-7.52 7.5 7.5 7.5 0 017.5 7.5c2.45 0 4.66-1.18 6.03-2.99A9.99 9.99 0 0112.43 2.3z"/>
          </svg>
          <!-- 太阳图标（日间模式） -->
          <svg v-else viewBox="0 0 24 24" fill="currentColor" width="18" height="18">
            <path d="M12 7a5 5 0 100 10 5 5 0 000-10zM12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
          </svg>
        </button>
        <button class="topnav-icon-btn" title="通知">
          <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18">
            <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/>
          </svg>
          <span v-if="notificationCount > 0" class="notif-dot">{{ notificationCount }}</span>
        </button>
        <div class="user-chip">
          <span class="org-name">山东财经大学</span>
          <div class="divider"></div>
          <div class="user-avatar">管</div>
          <span class="user-name">运维管理员</span>
        </div>
      </div>
    </nav>
    
    <main class="main-content">
      <router-view />
    </main>

    <!-- 浮动数字人窗口 (全 SVG 图标化) -->
    <div class="floating-window" :class="{ minimized: isMinimized, 'vad-active': continuousMode }">
      <div class="fw-header" @click="isMinimized && toggleMinimize()">
        <!-- 待确认倒计时角标（右上角） -->
        <div
          v-if="pendingCountdown > 0"
          class="confirm-badge"
          :class="{ urgent: pendingCountdown <= 5, warning: pendingCountdown <= 10 && pendingCountdown > 5 }"
          :title="`还有 ${pendingCountdown} 秒自动取消`"
        >
          <!-- 进度环：环上颜色随剩余时间从绿→黄→红 -->
          <svg class="badge-ring" viewBox="0 0 36 36">
            <circle class="ring-bg" cx="18" cy="18" r="15.5" />
            <circle
              class="ring-fg"
              cx="18" cy="18" r="15.5"
              :stroke-dasharray="97.4"
              :stroke-dashoffset="97.4 * (1 - pendingCountdown / Math.max(pendingTotal, 1))"
            />
          </svg>
          <div class="badge-inner">
            <span class="badge-icon">⏱</span>
            <span class="badge-num">{{ pendingCountdown }}</span>
          </div>
        </div>
        <div class="fw-avatar-wrapper">
          <img src="@/assets/avatar.jpg" alt="智能助手" class="fw-avatar-img" />
          <div class="online-indicator"></div>
        </div>
        <div class="fw-info" v-show="!isMinimized">
          <span class="fw-name">智能助手</span>
          <span class="fw-status">随时为您服务</span>
        </div>
        <div class="fw-header-actions" v-show="!isMinimized">
          <!-- 持续聆听开关 -->
          <button
            class="fw-icon-btn vad-toggle"
            :class="{ on: continuousMode }"
            @click.stop="toggleContinuousMode"
            :title="continuousMode ? '关闭持续聆听' : '开启持续聆听'"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path v-if="!continuousMode" d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
              <path v-else d="M12 15c1.66 0 2.99-1.34 2.99-3L15 6c0-1.66-1.34-3-3-3S9 4.34 9 6v6c0 1.66 1.34 3 3 3zm-1.2-9.1c-.66-.58-.8-1.44-.8-1.9h4c0 .46-.14 1.32-.8 1.9l-.6.5-.6-.5zm3.7 3.5c.16.4.25.83.25 1.3v.28l-2.45-2.45c.11.03.22.05.33.08l1.87 1.79zm2.5 0L19 8.2l-1.77-1.77-1.14 1.14L17.5 9zm-8.09 2.71L4.27 3 3 4.27 7.73 9H3v6h4l5 5v-6.73l2.83 2.83c-.5.39-1.06.71-1.66.9v2.06c1.11-.31 2.15-.81 3.09-1.46L21 20.73 19.73 22l-4.81-4.81L12 14.18V4L9.91 6.09 6.5 2.68l1.59 1.59C8.44 4.17 9 4 9 4l3 3V4z"/>
            </svg>
          </button>
          <button class="fw-icon-btn" @click.stop="toggleMute" :title="isMuted ? '取消静音' : '静音'">
            <svg v-if="!isMuted" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.11-.31 2.15-.81 3.09-1.46l2.18 2.18L21 20.73 4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
            </svg>
          </button>
          <!-- 音量滑块 -->
          <div class="volume-control" title="音量">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" class="vol-icon">
              <path v-if="volume > 0" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
              <path v-else d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.11-.31 2.15-.81 3.09-1.46l2.18 2.18L21 20.73 4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
            </svg>
            <input type="range" min="0" max="1" step="0.05" :value="volume"
              @input="setVolume(($event.target as HTMLInputElement).valueAsNumber)"
              class="vol-slider" />
          </div>
          <button class="fw-icon-btn" @click.stop="toggleMinimize" title="最小化">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M19 13H5v-2h14v2z"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- VAD 状态栏 -->
      <div v-if="continuousMode" class="vad-bar" :class="vadState" v-show="!isMinimized">
        <span v-if="vadState === 'listening'" class="vad-msg">🎧 正在聆听...</span>
        <span v-else-if="vadState === 'speaking'" class="vad-msg">🎙️ 识别中...</span>
        <span v-else-if="vadState === 'processing'" class="vad-msg">🤔 思考中...</span>
      </div>

      <!-- TTS 语音设置面板（语速 + 音色） -->
      <div v-if="showTtsSettings" class="tts-settings-panel" v-show="!isMinimized">
        <div class="tts-setting-row">
          <span class="tts-setting-label">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" style="margin-right:4px"><path d="M13 2.05v2.02c3.46.82 6 3.97 6 7.93s-2.54 7.11-6 7.93v2.02c4.01-.86 7-4.99 7-9.95s-2.99-9.09-7-9.95zm-2 0C6.99 2.91 4 7.04 4 12s2.99 9.09 7 9.95v-2.02c-3.46-.82-6-3.97-6-7.93s2.54-7.11 6-7.93V2.05z"/></svg>
            语速
          </span>
          <span class="tts-setting-val">{{ speed }}x</span>
          <input type="range" min="0.5" max="2.0" step="0.05" :value="speed"
            @input="setSpeed(($event.target as HTMLInputElement).valueAsNumber)"
            class="tts-slider" />
        </div>
        <div class="tts-setting-row">
          <span class="tts-setting-label">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" style="margin-right:4px"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>
            音色
          </span>
          <select v-model="selectedVoice" @change="setVoice(selectedVoice)" class="tts-voice-select">
            <option v-for="v in availableVoices" :key="v.id" :value="v.id">
              {{ v.name }} ({{ v.gender === 'female' ? '女' : '男' }})
            </option>
          </select>
        </div>
      </div>

      <button class="tts-settings-toggle" @click.stop="showTtsSettings = !showTtsSettings" v-show="!isMinimized" :title="showTtsSettings ? '收起设置' : '语音设置'">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="margin-right:4px"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94L14.4 2.81c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41L9.25 5.35c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
          {{ showTtsSettings ? '收起' : '设置' }}
        </button>

      <div class="chat-area" v-show="!isMinimized">
        <div v-if="chatMessages.length === 0" class="chat-empty">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="#d1d5db" style="margin-bottom:12px;">
            <path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4L12 2zm0 5l-1.1 3.9L7 12l3.9 1.1L12 17l1.1-3.9L17 12l-3.9-1.1L12 7z"/>
          </svg>
          <p>您好！我是您的智能助理，<br/>请按住下方按钮告诉我您的需求。</p>
        </div>
        <div v-else class="chat-toolbar">
          <span class="chat-toolbar-count">{{ chatMessages.length }} 条消息</span>
          <button class="chat-clear-btn" @click="clearChat" title="清空聊天记录">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            清空
          </button>
        </div>
        <div v-for="(msg, i) in chatMessages" :key="i" class="chat-row" :class="msg.type">
          <div class="chat-bubble">{{ msg.text }}</div>
        </div>
      </div>

      <div class="fw-footer" v-show="!isMinimized">
        <!-- 🔥 实时转写显示区 -->
        <div v-if="isRecording && realtimeText && !continuousMode" class="realtime-transcript">
          <svg class="realtime-icon" viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
            <path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
          </svg>
          <span class="realtime-wave"></span>
          <span class="realtime-txt">{{ realtimeText }}</span>
          <span class="realtime-cursor">|</span>
        </div>

        <!-- TTS 播放控制条 -->
        <div v-if="ttsState !== 'idle'" class="tts-controls">
          <button class="tts-btn" v-if="ttsState === 'playing'" @click="pauseTTS" title="暂停">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
          </button>
          <button class="tts-btn" v-if="ttsState === 'paused'" @click="resumeTTS" title="继续">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          </button>
          <button class="tts-btn" @click="stopTTS" title="停止">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
          </button>
          <span class="tts-label">
            {{ ttsState === 'playing' ? '🔊 正在播报' : '⏸️ 已暂停' }}
          </span>
        </div>

        <button
          v-if="!continuousMode"
          class="fw-record-btn"
          :class="{ recording: isRecording }"
          @click="toggleRecording"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
          </svg>
          <span class="btn-text">{{ isRecording ? '点击停止录音' : '点击开始说话' }}</span>
        </button>
        <div v-else class="fw-listening-btn" :class="vadState">
          <span class="pulse-dot"></span>
          <span>{{ vadState === 'listening' ? '🎧 连续聆听中' : vadState === 'speaking' ? '🎙️ 识别中' : '🤔 思考中...' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background: #f0f2f5;
  color: #1f2937;
}
</style>

<style scoped>
#app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ==========================================
   深色顶栏 - 真实业务系统风格
   ========================================== */
.topnav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  padding: 0 16px;
  background: #001529;
  box-shadow: 0 1px 4px rgba(0,21,41,0.08);
  position: sticky;
  top: 0;
  z-index: 10001;
}
.topnav-left {
  display: flex;
  align-items: center;
  gap: 24px;
}
.brand-area {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.brand-text {
  font-size: 18px;
  font-weight: 700;
  font-style: italic;
  color: #ffffff;
  letter-spacing: 3.5px;
  white-space: nowrap;
}
.nav-links {
  display: flex;
  height: 60px;
  margin-left: 60px;
}
.nav-item {
  position: relative;
  height: 100%;
  padding: 0 16px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.65);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-icon {
  flex-shrink: 0;
  opacity: 0.8;
}
.nav-item:hover .nav-icon,
.nav-item.active .nav-icon {
  opacity: 1;
}
.nav-item:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.05);
}
.nav-item.active {
  color: #ffffff;
  background: #1890ff;
  font-weight: 500;
}
.topnav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.topnav-icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.65);
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.topnav-icon-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}
.notif-dot {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 14px;
  height: 14px;
  padding: 0 4px;
  background: #f5222d;
  color: #fff;
  font-size: 10px;
  border-radius: 7px;
  border: 1px solid #001529;
  display: flex;
  align-items: center;
  justify-content: center;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 8px;
}
.org-name {
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
}
.divider {
  width: 1px;
  height: 16px;
  background: rgba(255, 255, 255, 0.2);
}
.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  background: #1890ff;
  color: #fff;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.user-name {
  color: #fff;
  font-size: 13px;
}
.main-content {
  flex: 1;
  zoom: 0.85;
}

/* ========== 浮动数字人窗口 ========== */
.floating-window {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 320px;
  max-height: 85vh;
  background: #ffffff;
  border-radius: 18px;
  box-shadow: 0 6px 16px -8px rgba(0,0,0,0.08), 0 9px 28px 0 rgba(0,0,0,0.05), 0 12px 48px 16px rgba(0,0,0,0.03);
  display: flex;
  flex-direction: column;
  overflow: visible;
  z-index: 10001;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid #e8e8e8;
}
.floating-window.minimized {
  width: 52px;
  height: 52px;
  border-radius: 26px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.floating-window.minimized:hover {
  transform: scale(1.05);
}
.fw-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #ffffff;
  border-bottom: 1px solid #f0f0f0;
  position: relative;
  border-radius: 18px 18px 0 0;
}
.floating-window.minimized .fw-header {
  padding: 6px;
  justify-content: center;
  border: none;
  height: 100%;
  border-radius: 26px;
}
.fw-avatar-wrapper {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: #f1f5f9;
}
.fw-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
  display: block;
}
.online-indicator {
  position: absolute;
  bottom: 0px;
  right: 0px;
  width: 8px;
  height: 8px;
  background: #52c41a;
  border: 1.5px solid #ffffff;
  border-radius: 50%;
  z-index: 2;
  box-shadow: 0 0 0 1px rgba(82, 196, 26, 0.3);
}
.fw-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.fw-name {
  font-size: 14px;
  font-weight: 600;
  color: #262626;
}
.fw-status {
  font-size: 11px;
  color: #8c8c8c;
}
.fw-header-actions {
  display: flex;
  gap: 4px;
}
.fw-icon-btn {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #8c8c8c;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.fw-icon-btn:hover {
  background: #f5f5f5;
  color: #262626;
}

/* ---- 音量控制 ---- */
.volume-control {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  border-radius: 4px;
  transition: background 0.2s;
}
.volume-control:hover { background: #f5f5f5; }
.vol-icon { color: #8c8c8c; flex-shrink: 0; }
.vol-slider {
  width: 40px;
  height: 3px;
  -webkit-appearance: none;
  appearance: none;
  background: #d9d9d9;
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.vol-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #1890ff;
  cursor: pointer;
}

/* ---- 持续聆听开关按钮 ---- */
.vad-toggle.on {
  color: #52c41a;
  background: #f6ffed;
}
.vad-toggle.on:hover {
  background: #d9f7be;
  color: #389e0d;
}

/* ---- VAD 状态栏 ---- */
.vad-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  transition: background 0.3s;
}
.vad-bar.listening { background: #f6ffed; color: #389e0d; }
.vad-bar.speaking  { background: #fffbe6; color: #d48806; }
.vad-bar.processing { background: #e6f7ff; color: #096dd9; }
.vad-msg {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ---- 持续聆听按钮（替代按住说话） ---- */
.fw-listening-btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: default;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.3s;
  box-sizing: border-box;
  overflow: hidden;
  white-space: nowrap;
}
.fw-listening-btn.listening  { background: #f6ffed; color: #389e0d; }
.fw-listening-btn.speaking   { background: #fffbe6; color: #d48806; }
.fw-listening-btn.processing { background: #e6f7ff; color: #096dd9; }

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.listening .pulse-dot {
  animation: vadPulse 1.5s infinite;
}
@keyframes vadPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: 0.4; transform: scale(1.5); }
}

/* 浮动窗口 - 持续聆听激活光环 */
.floating-window.vad-active {
  box-shadow: 0 0 0 3px rgba(82, 196, 26, 0.25), 0 6px 16px -8px rgba(0,0,0,0.08);
}
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  min-height: 160px;
  background: #fafafa;
}
.chat-empty {
  text-align: center;
  color: #bfbfbf;
  font-size: 13px;
  padding: 40px 0;
  line-height: 1.6;
}
.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 6px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 4px;
  flex-shrink: 0;
}
.chat-toolbar-count {
  font-size: 12px;
  color: #bfbfbf;
}
.chat-clear-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #8c8c8c;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.2s;
}
.chat-clear-btn:hover {
  color: #ff4d4f;
  background: #fff1f0;
}
.chat-row {
  display: flex;
  animation: bubbleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.chat-row.user {
  justify-content: flex-end;
}
.chat-row.assistant {
  justify-content: flex-start;
}
.chat-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
.chat-row.user .chat-bubble {
  background: #1890ff;
  color: #ffffff;
}
.chat-row.assistant .chat-bubble {
  background: #ffffff;
  color: #262626;
  border: 1px solid #f0f0f0;
}
.fw-footer {
  padding: 12px;
  background: #ffffff;
  border-top: 1px solid #f0f0f0;
  border-radius: 0 0 18px 18px;
}

/* ===== 实时转写显示 ===== */
.realtime-transcript {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 10px;
  background: linear-gradient(135deg, #e6f7ff 0%, #f0f5ff 100%);
  border: 1px solid #91d5ff;
  border-radius: 8px;
  animation: realtimeFadeIn 0.2s ease;
}
@keyframes realtimeFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
.realtime-icon {
  color: #1890ff;
  flex-shrink: 0;
  animation: micPulse 1.2s ease-in-out infinite;
}
@keyframes micPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.realtime-wave {
  width: 4px;
  height: 16px;
  background: #1890ff;
  border-radius: 2px;
  flex-shrink: 0;
  animation: waveAnim 0.6s ease-in-out infinite alternate;
}
@keyframes waveAnim {
  from { height: 6px; }
  to { height: 18px; }
}
.realtime-txt {
  flex: 1;
  font-size: 14px;
  color: #0050b3;
  line-height: 1.4;
  word-break: break-all;
}
.realtime-cursor {
  font-size: 16px;
  color: #1890ff;
  font-weight: bold;
  animation: blink 0.8s step-end infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ---- TTS 设置面板（语速 + 音色） ---- */
.tts-settings-toggle {
  width: 100%;
  padding: 6px 12px;
  border: none;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
  color: #8c8c8c;
  font-size: 11px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.tts-settings-toggle:hover { background: #f0f0f0; color: #1890ff; }
.tts-settings-panel {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tts-setting-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tts-setting-label {
  font-size: 11px;
  color: #595959;
  white-space: nowrap;
  display: flex;
  align-items: center;
}
.tts-setting-val {
  font-size: 12px;
  font-weight: 600;
  color: #1890ff;
  min-width: 32px;
  text-align: right;
}
.tts-slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 4px;
  border-radius: 2px;
  background: #d9d9d9;
  outline: none;
  cursor: pointer;
}
.tts-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #1890ff;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
  cursor: pointer;
}
.tts-voice-select {
  flex: 1;
  min-width: 0;           /* 允许收缩，防止长音色名撑破面板 */
  max-width: 100%;
  width: 100%;
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  background: #fff;
  cursor: pointer;
  outline: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tts-voice-select:focus { border-color: #1890ff; }

/* ---- 夜间模式 TTS 设置 ---- */
html.dark .tts-settings-toggle { background: #1e293b; color: #94a3b8; border-bottom-color: #334155; }
html.dark .tts-settings-toggle:hover { background: #334155; color: #3b82f6; }
html.dark .tts-settings-panel { background: #1e293b; border-bottom-color: #334155; }
html.dark .tts-setting-label { color: #cbd5e1; }
html.dark .tts-slider { background: #475569; }
html.dark .tts-voice-select { background: #0f172a; color: #e2e8f0; border-color: #475569; }

/* ---- TTS 播放控制条 ---- */
.tts-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 10px;
  background: #f6f8fa;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
}
.tts-btn {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #595959;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.tts-btn:hover { border-color: #1890ff; color: #1890ff; background: #e6f7ff; }
.tts-label {
  font-size: 12px;
  color: #8c8c8c;
  font-weight: 500;
}
.fw-record-btn {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 6px;
  background: #1890ff;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
  user-select: none;
  -webkit-user-select: none;
}
.fw-record-btn:hover {
  background: #40a9ff;
}
.fw-record-btn.recording {
  background: #f5222d;
  animation: pulse-red 1.5s infinite;
}
@keyframes pulse-red {
  0% { box-shadow: 0 0 0 0 rgba(245, 34, 45, 0.4); }
  70% { box-shadow: 0 0 0 8px rgba(245, 34, 45, 0); }
  100% { box-shadow: 0 0 0 0 rgba(245, 34, 45, 0); }
}
@keyframes bubbleIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.chat-area::-webkit-scrollbar { width: 6px; }
.chat-area::-webkit-scrollbar-track { background: transparent; }
.chat-area::-webkit-scrollbar-thumb { background: #d9d9d9; border-radius: 3px; }
.chat-area::-webkit-scrollbar-thumb:hover { background: #bfbfbf; }

/* ========== 待确认倒计时角标（浮窗右上角）========== */
.confirm-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 38px;
  height: 38px;
  z-index: 10;
  animation: badge-pop 0.3s ease-out;
}
.badge-ring {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
  filter: drop-shadow(0 2px 4px rgba(245, 34, 45, 0.3));
}
.ring-bg {
  fill: none;
  stroke: #f0f0f0;
  stroke-width: 3;
}
.ring-fg {
  fill: none;
  stroke: #52c41a;        /* 默认绿色（>10s）*/
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.95s linear, stroke 0.3s;
}
.confirm-badge.warning .ring-fg { stroke: #faad14; }   /* 黄色（<=10s）*/
.confirm-badge.urgent  .ring-fg { stroke: #f5222d; }   /* 红色（<=5s）*/
.badge-inner {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  border-radius: 50%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  border: 2px solid currentColor;
  color: #52c41a;
}
.confirm-badge.warning .badge-inner { color: #faad14; }
.confirm-badge.urgent  .badge-inner {
  color: #f5222d;
  animation: pulse-red 1s infinite;
}
.badge-icon { font-size: 8px; line-height: 1; margin-bottom: 1px; }
.badge-num  { font-size: 14px; font-weight: 700; line-height: 1; }
@keyframes badge-pop {
  0%   { transform: scale(0); opacity: 0; }
  60%  { transform: scale(1.15); }
  100% { transform: scale(1); opacity: 1; }
}
</style>

<style>
/* ==========================================
   夜间模式 — 全局覆盖（非 scoped，直接在 <html class="dark"> 时生效）
   ========================================== */
html.dark body {
  background: #0f172a;
  color: #e2e8f0;
}

html.dark .main-content {
  background: #0f172a;
}

html.dark .home-page {
  background: #0f172a;
}

html.dark .card {
  background: #1e293b !important;
  border-color: #334155 !important;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3) !important;
}

html.dark .card-head {
  border-bottom-color: #334155 !important;
}

html.dark .card-head-title {
  color: #e2e8f0 !important;
}

html.dark .card-body {
  color: #cbd5e1;
}

html.dark .urgent-text,
html.dark .notice-line,
html.dark .log-text {
  color: #cbd5e1 !important;
}

html.dark .log-text strong {
  color: #f1f5f9 !important;
}

html.dark .urgent-row,
html.dark .log-row {
  border-bottom-color: #334155 !important;
}

html.dark .split-line {
  background: #334155 !important;
}

html.dark .quick-btn {
  background: #1e293b !important;
  border-color: #334155 !important;
  color: #cbd5e1 !important;
}

html.dark .quick-btn:hover {
  border-color: #3b82f6 !important;
  color: #3b82f6 !important;
  background: #1e3a5f !important;
}

html.dark .empty {
  color: #64748b !important;
}

/* ========== 夜间模式 — 工单列表页 ========== */
html.dark .tickets-page {
  background: #0f172a;
}

html.dark .page-title {
  color: #f1f5f9 !important;
}

html.dark .control-bar {
  background: #1e293b !important;
  border-color: #334155 !important;
}

html.dark .filter-select,
html.dark .search-input {
  background: #0f172a !important;
  color: #e2e8f0 !important;
  border-color: #475569 !important;
}

html.dark .filter-select:focus,
html.dark .search-input:focus {
  border-color: #3b82f6 !important;
}

html.dark .main-table {
  background: #1e293b !important;
  color: #e2e8f0;
}

html.dark .main-table thead {
  background: #334155 !important;
}

html.dark .main-table thead th {
  color: #cbd5e1 !important;
}

html.dark .main-table tbody td {
  color: #e2e8f0 !important;
}

html.dark .main-table tbody tr {
  border-bottom-color: #334155 !important;
}

html.dark .main-table tbody tr:hover {
  background: #334155 !important;
}

html.dark .id-font {
  color: #94a3b8 !important;
}

html.dark .time-font {
  color: #94a3b8 !important;
}

html.dark .empty-row {
  color: #64748b !important;
}

html.dark .pagination {
  border-top-color: #334155 !important;
}

html.dark .page-btn {
  background: #334155 !important;
  color: #cbd5e1 !important;
  border-color: #475569 !important;
}

html.dark .page-btn:hover:not(:disabled) {
  background: #475569 !important;
}

html.dark .page-info {
  color: #94a3b8 !important;
}

html.dark .drawer-panel {
  background: #1e293b !important;
}

html.dark .drawer-mask {
  background: rgba(0, 0, 0, 0.6) !important;
}

html.dark .drawer-header {
  border-bottom-color: #334155 !important;
}

html.dark .drawer-header h3 {
  color: #f1f5f9 !important;
}

html.dark .info-row .label {
  color: #94a3b8 !important;
}

html.dark .info-row .value {
  color: #e2e8f0 !important;
}

html.dark .timeline-item {
  border-left-color: #475569 !important;
}

html.dark .timeline-content {
  color: #cbd5e1 !important;
}

html.dark .timeline-more {
  color: #64748b !important;
}

html.dark .status-tag {
  background: rgba(59, 130, 246, 0.15) !important;
}

html.dark .loading-tip {
  color: #64748b !important;
}

/* ========== 夜间模式 — 浮动窗口 ========== */
html.dark .floating-window {
  background: #1e293b !important;
  border-color: #334155 !important;
}

html.dark .fw-header {
  background: #1e293b !important;
  border-bottom-color: #334155 !important;
}

html.dark .fw-name {
  color: #f1f5f9 !important;
}

html.dark .fw-subtitle {
  color: #94a3b8 !important;
}

html.dark .fw-body {
  background: #0f172a !important;
}

html.dark .chat-area {
  background: #0f172a !important;
}

html.dark .chat-toolbar {
  border-bottom-color: #334155 !important;
}
html.dark .chat-toolbar-count {
  color: #64748b !important;
}
html.dark .chat-clear-btn {
  color: #94a3b8 !important;
}
html.dark .chat-clear-btn:hover {
  color: #f87171 !important;
  background: #451a1a !important;
}

html.dark .chat-bubble {
  background: #334155 !important;
  color: #e2e8f0 !important;
}

html.dark .chat-bubble.user {
  background: #1e3a5f !important;
}

html.dark .fw-input-row {
  border-top-color: #334155 !important;
}

html.dark .fw-text-input {
  background: #334155 !important;
  color: #e2e8f0 !important;
}

html.dark .fw-record-btn {
  background: #334155 !important;
  color: #cbd5e1 !important;
}

html.dark .fw-record-btn.recording {
  background: #7f1d1d !important;
}

html.dark .fw-listening-btn {
  background: #1e3a5f !important;
  color: #93c5fd !important;
}

html.dark .confirm-badge .badge-inner {
  background: #1e293b !important;
}
</style>