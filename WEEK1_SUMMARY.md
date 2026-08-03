# 数字人智能助手 — 第一周开发总结

> 日期：2026-07-18 ~ 2026-07-19  
> 目标：搭建 **完全离线** 的数字人智能助手基础设施（语音输入→理解意图→执行操作→语音输出）

---

## 一、项目架构

```
🎤 麦克风录音 → 📝 FunASR 语音识别 → 🧠 Ollama Qwen2.5 理解意图
                                            ↓
🔊 Windows SAPI TTS 播报 ← ⚡ Flask 后端执行操作 ← JSON 意图解析
                                            ↓
                                   🌐 Vue3 前端展示（工单/监控）
```

**核心特点**：全程离线，不依赖任何互联网服务。

---

## 二、技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | Vue3 + Vite + Vue Router + Axios | SPA 页面（工单列表、监控大盘） |
| 后端 | Python Flask + flask-cors | REST API 服务 |
| 语音识别 | FunASR paraformer-zh | 中文离线识别，准确率高 |
| 大模型 | Ollama + Qwen2.5-7B (Q4量化) | 本地推理，约4-5GB显存 |
| 语音合成 | Windows SAPI (Microsoft Huihui) | 离线中文语音播报 |
| 音频采集 | PyAudio | 麦克风录音 |

---

## 三、依赖安装命令

### 3.1 Python 环境

```powershell
# 创建虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 后端依赖
pip install flask flask-cors requests

# ASR 依赖（注意：PyTorch 需单独安装）
pip install torch torchaudio --extra-index-url https://download.pytorch.org/whl/cpu
pip install funasr modelscope soundfile pyaudio

# TTS 依赖
pip install pyttsx3  # 后来弃用，改 Windows 原生 SAPI
```

### 3.2 前端环境

```powershell
# 安装 Node.js（winget 或官网下载）
winget install OpenJS.NodeJS.LTS

# 创建 Vue 项目
npm create vue@latest frontend
cd frontend
npm install
npm install vue-router@4 axios
npm run dev
```

### 3.3 大模型

```powershell
# 安装 Ollama（从 https://ollama.com 下载）
# 拉取模型
ollama pull qwen2.5:7b-instruct-q4_K_M
```

### 3.4 完整 requirements.txt

```
flask
flask-cors
requests
torch
torchaudio
funasr
modelscope
soundfile
pyaudio
pyttsx3          # 后来弃用
win32com         # 通过 pywin32 安装
```

---

## 四、项目文件结构

```
基于大模型驱动的数字人智能助手/
├── venv/                          # Python 虚拟环境
├── backend/
│   ├── app.py                     # Flask 主入口（路由+集成）
│   ├── asr_service.py             # 语音识别服务
│   ├── ollama_service.py          # 大模型意图理解服务
│   ├── tts_service.py             # 语音合成服务
│   ├── requirements.txt           # Python 依赖
│   ├── test_ollama.py             # Ollama 测试脚本
│   ├── test_asr.py                # ASR 测试脚本
│   ├── test_tts.py                # TTS 测试脚本
│   ├── record_and_recognize.py   # 录音+识别测试
│   └── integration_test.py       # 全链路整合测试
├── frontend/
│   └── src/
│       ├── api/index.ts           # Axios API 封装
│       ├── router/index.ts        # Vue Router 配置
│       ├── views/
│       │   ├── TicketsPage.vue    # 工单列表页
│       │   └── MonitorPage.vue    # 监控大盘页
│       ├── App.vue                # 根组件（导航栏）
│       └── main.ts                # 入口文件
├── tickets.txt                    # 工单 Mock 数据
├── servers.txt                    # 服务器监控 Mock 数据
└── readme.md                      # 项目说明
```

---

## 五、遇到的问题与解决方法

### 1. pyttsx3 多次调用只有第一句有声

**现象**：同一个引擎实例多次 say()+runAndWait() 后，只有第一次能听到声音。

**原因**：pyttsx3 在 Windows 上的已知 bug，引擎状态未正确重置。

**解决**：放弃 pyttsx3，改用 **Windows 原生 SAPI**（`win32com.client.Dispatch("SAPI.SpVoice")`），每次播报新建引擎实例+预热空播报。

---

### 2. TTS 播报开头吞字

**现象**：语音播报时第一个字听不到。

**原因**：音频设备需要"预热"，第一次播报时设备尚未就绪。

**解决**：正式播报前先发一个空播报 `voice.Speak("", 1)` + `time.sleep(0.4)` 激活音频通道。

---

### 3. ASR 录音开头被截断

**现象**：录音识别时漏掉开头几个字，如"有两个工单"识别为"个工单"。

**原因**：固定时长录音+倒计时机制让用户不知道何时开始说话。

**解决**：添加 3-2-1 倒计时，清空麦克风缓冲区，增加录音时长到 5 秒。

---

### 4. FunASR 断网后每次都尝试联网

**现象**：断网后 `AutoModel()` 加载时长时间重试连接 `modelscope`，报 `ConnectionResetError(10054)`。

**原因**：modelscope hub 默认每次检查模型更新，`disable_update=True` 只禁用 funasr 自身检查。

**解决**：直接传**本地缓存路径**加载模型，完全跳过 hub：

```python
_CACHE = os.path.expanduser("~/.cache/modelscope/models")
_ASR_DIR = os.path.join(_CACHE, "iic--speech_paraformer-...", "snapshots", "master")
AutoModel(model=_ASR_DIR, ...)
```

---

### 5. Ollama HTTP 500 错误

**现象**：`POST /api/generate` 返回 `500 Server Error`。

**原因**：模型尚未加载到显存中，第一次调用需等待加载。

**解决**：先手动运行 `ollama run qwen2.5:7b-instruct-q4_K_M` 触发加载，或给 API 调用更长的超时时间。

---

### 6. Flask jsonify 中文显示为 \uXXXX

**现象**：API 返回的中文被转义成 Unicode 编码。

**解决**：在 Flask app 中设置 `app.json.ensure_ascii = False`。

---

### 7. PowerShell curl 报参数绑定错误

**现象**：`curl -H` 在 PowerShell 中报 `InvalidArgument`。

**原因**：PowerShell 中 `curl` 是 `Invoke-WebRequest` 的别名，参数语法不同。

**解决**：使用 `curl.exe` 或 `Invoke-RestMethod`（简写 `irm`）。

---

### 8. npm create vue 报 node 未找到

**原因**：Node.js 未安装。

**解决**：`winget install OpenJS.NodeJS.LTS`，安装后重开终端。

---

## 六、API 接口汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 健康检查 |
| POST | `/chat` | 对话接口（文本/音频→意图→回复+TTS） |
| GET | `/api/tickets/stat` | 工单状态统计 |
| GET | `/api/servers/metrics` | 服务器监控指标 |
| POST | `/api/tickets/update` | 模拟修改工单状态 |

---

## 七、启动方式

```powershell
# 终端 1：Flask 后端
cd backend && python app.py

# 终端 2：Vue 前端
cd frontend && npm run dev

# 终端 3：语音对话测试
cd backend && python integration_test.py
```

浏览器打开 `http://localhost:5173` 访问前端界面。

---

## 八、下一步计划

- [ ] 前端添加录音按钮，实现 Web 端语音交互
- [ ] 接入实时 VAD（语音活动检测），替代固定时长录音
- [ ] 完善 Ollama Prompt，覆盖更多业务场景
- [ ] 将 Mock 数据换成真实数据库（SQLite/MySQL）
- [ ] 优化 TTS 音色（尝试 VITS 或其他离线方案）
