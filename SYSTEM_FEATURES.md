# 数字人智能助手 — 系统功能总结

> 生成日期：2026-07-21

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Vue 3)                  │
│  浮窗助手 UI  │  监控大盘页  │  工单概览页          │
└──────────┬──────────────────────────┬────────────────┘
           │ HTTP / Axios              │
┌──────────▼──────────────────────────▼────────────────┐
│                   Backend (Flask)                    │
│  /chat  │  /api/transcribe  │  /api/tts             │
│  /api/tickets/*  │  /api/servers/metrics            │
├──────────┬──────────┬──────────┬────────────────────┤
│ ASR服务  │ LLM服务  │ TTS服务  │  DB服务            │
│ FunASR   │ Ollama   │ SAPI     │  SQL Server        │
└──────────┴──────────┴──────────┴────────────────────┘
```

---

## 二、核心功能模块

### 1️⃣ 语音识别（ASR）— `backend/asr_service.py`

| 特性 | 说明 |
|---|---|
| 引擎 | FunASR + paraformer-zh（完全离线） |
| 模型缓存 | Modelscope 本地缓存，无需联网 |
| VAD 端点检测 | 句尾静音 800ms 截断，句首静音 300ms 容忍 |
| 多输入格式 | 支持文件路径、bytes 字节、base64 三种输入 |
| 采样率 | 自动处理 16kHz 单声道 WAV |

---

### 2️⃣ 大语言模型（LLM）— `backend/ollama_service.py`

| 特性 | 说明 |
|---|---|
| 模型 | qwen2.5:7b-instruct-q4_K_M（本地 Ollama） |
| 意图理解 | 输出严格 JSON：`query` / `navigate` / `operate` / `greeting` / `unknown` |
| 数据总结 | 将原始数据用自然语言总结给用户 |
| 对话历史 | 保留最近 20 轮上下文 |

**支持的意图动作：**

| 意图 | 示例指令 | 后端动作 |
|---|---|---|
| `query` → `tickets_stat` | "查工单"、"未完成的工单" | 从 DB 查询工单统计 |
| `query` → `tickets_detail` | "查工单 5 号" | 从 DB 查询单个工单详情 |
| `query` → `servers_metrics` | "服务器状态"、"监控" | 从 DB 查询最新监控指标 |
| `navigate` → `/tickets` | "打开工单" | 前端跳转工单页 |
| `navigate` → `/monitor` | "打开监控"、"看大盘" | 前端跳转监控页 |
| `operate` → `tickets_update` | "把工单 5 标为已完成" | 二次确认后写入 DB |

---

### 3️⃣ 语音合成（TTS）— `backend/tts_service.py`

| 特性 | 说明 |
|---|---|
| 引擎 | Windows SAPI（win32com，完全离线） |
| 回退方案 | pyttsx3（当 SAPI 不可用时） |
| 输出格式 | WAV 音频流（通过 `/api/tts` 返回） |
| 中文语音 | 自动选择系统中英文语音 |
| 异步队列 | 后台线程播放，不阻塞 API 请求 |

---

### 4️⃣ 对话与操作引擎 — `backend/app.py`

| 特性 | 说明 |
|---|---|
| 双模输入 | 纯文本 或 前端录音后语音识别 |
| 对话历史 | 最近 20 轮上下文记忆 |
| 二次确认 | 修改工单状态前询问「确认/取消」 |
| 状态管理 | `chat_history` + `pending_operation` 全局状态 |
| 错误处理 | 404/500 统一 JSON 错误响应 |

---

### 5️⃣ 数据库服务 — `backend/db_service.py`

| 特性 | 说明 |
|---|---|
| 数据库 | SQL Server（ODBC Driver 17） |
| 数据库名 | OpsCenter |
| 表结构 | `tickets`（工单表）、`server_metrics`（监控表） |
| 建表 | 自动检测并创建缺失表 |
| 数据导入 | 从 `mock_data.py` 导入 50 条工单 + 监控数据 |
| 查询接口 | `get_tickets()`、`get_ticket_by_id()`、`get_tickets_stat()` |
| 写入接口 | `update_ticket_status()` |
| 监控接口 | `get_latest_metrics()` |

---

### 6️⃣ 前端浮窗助手 — `frontend/src/App.vue`

| 特性 | 说明 |
|---|---|
| 布局 | 固定右下角浮动窗口，可拖拽 |
| 头像 | 卡通数字人动画头像 |
| 对话气泡 | 用户 & 助手消息列表，自动滚动 |
| 录音按钮 | 按住录音 → 松手发送 → ASR → LLM → TTS 播报 |
| TTS 播放 | 自动播报助手回复语音 |
| 静音开关 | 可关闭 TTS 语音播报 |
| 最小化 | 可收起为小图标 |
| 页面导航 | 支持跳转到工单/监控页面 |

---

### 7️⃣ 前端页面

| 页面 | 路由 | 功能 |
|---|---|---|
| 监控大盘 | `/monitor` | 展示 CPU、内存、磁盘、网络指标卡片 |
| 工单概览 | `/tickets` | 展示工单总数、状态分布、优先级分布 |

---

## 三、API 接口一览

| 方法 | 路径 | 功能 | 数据源 |
|---|---|---|---|
| GET | `/` | 健康检查 | — |
| POST | `/chat` | 对话（文本/语音） | DB |
| POST | `/api/transcribe` | 上传音频文件转文字 | FunASR |
| POST | `/api/tts` | 文本合成语音（返回 WAV） | SAPI |
| POST | `/api/chat/reset` | 重置对话历史 | — |
| GET | `/api/tickets/stat` | 工单统计 | DB |
| GET | `/api/servers/metrics` | 最新监控指标 | DB |
| POST | `/api/tickets/update` | 修改工单状态 | DB |
| GET | `/api/tickets/<id>` | 查看单条工单 | DB |
| GET | `/api/debug/pending` | 查看待确认操作（调试） | 内存 |

---

## 四、技术栈

| 层级 | 技术 |
|---|---|
| 前端框架 | Vue 3 + Vite + TypeScript |
| 前端路由 | Vue Router |
| HTTP 客户端 | Axios |
| 后端框架 | Python Flask |
| 语音识别 | FunASR（paraformer-zh，离线） |
| 大语言模型 | Ollama（qwen2.5:7b-instruct-q4_K_M） |
| 语音合成 | Windows SAPI（离线） |
| 数据库 | SQL Server + pyodbc |
| 音频处理 | ffmpeg（16kHz 单声道 WAV 转换） |

---

## 五、部署依赖

### 后端
```bash
pip install -r backend/requirements.txt
```

### 前端
```bash
cd frontend && npm install
```

### 外部依赖
- Ollama 服务运行在 `http://localhost:11434`
- SQL Server 运行在 `127.0.0.1`，数据库 `OpsCenter`
- ffmpeg 安装在 `C:\ffmpeg\bin`
- FunASR 模型已缓存到 `~/.cache/modelscope`

---

## 六、已知待完善

| 事项 | 说明 |
|---|---|
| 前端完整工单列表页 | 当前仅有统计卡片，缺少可交互的工单表格 |
| 前端监控页图表 | 当前仅展示数字卡片，缺少趋势折线图 |
| 历史监控数据 | 当前只取最新一条，无时间范围查询 |
| 用户认证 | 暂无登录/权限体系 |
| 错误 UI | 前端对后端错误缺少统一提示组件 |
