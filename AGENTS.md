# AGENTS.md — 轻言OPS 编码指南

> 轻言OPS：基于大模型驱动的数字人智能助手，面向 IT 运维场景的语音交互平台。
> 详细架构说明见 [readme.md](./readme.md) 和 [SYSTEM_FEATURES.md](./SYSTEM_FEATURES.md)。

## 启动命令

```powershell
# 后端 (Flask, 端口 5000)
cd backend && ..\venv\Scripts\activate && python app.py

# 前端 (Vite dev server)
cd frontend && npm run dev

# 运行测试
cd backend/tests && python test_api.py
```

## 技术栈速览

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12+, Flask 3.1, pyodbc |
| 前端 | Vue 3 + TypeScript + Vite 8, Pinia, ECharts 6 |
| 数据库 | SQL Server 2019+, ODBC Driver 17, 数据库 `OpsCenter` |
| LLM | Ollama + `qwen3:8b` (temperature=0.1, 本地推理) |
| 语音 | FunASR (`paraformer-zh`) 离线识别, edge-tts → SAPI 降级 TTS |
| 音频 | ffmpeg: `C:\ffmpeg\bin`, WebM→WAV 16kHz 单声道 |

## 核心架构约定

### 1. 对话状态机 (FSM) — 最重要

`backend/chat_state.py` 定义了 5 状态：
`IDLE → PROCESSING → REPLYING → IDLE`，带 `AWAITING_CONFIRMATION` 分支。

- **任何修改/删除/排班操作必须先进入 `AWAITING_CONFIRMATION`**，等用户说"确认"才执行
- 30 秒超时自动取消，通过 `last_entity` 实现指代消解
- 修改意图处理时，务必保持状态机流转一致性

### 2. 意图解析双重策略

- **第一步：规则预检** (`app.py` 正则匹配) — 高频场景（导航/简单排班查询）绕过 LLM
- **第二步：LLM 解析** (`ollama_service.py`) — 复杂意图，失败自动降级重试
- LLM 输出为**严格 JSON**，11 类意图：`navigate/query/query_monitor/staff_query/schedule_query/operate/delete/summary/search/greeting/unknown`

### 3. 全离线运行

FunASR + Ollama + edge-tts/SAPI 全部本地运行。`app.py` 启动时强制检查：
- 必须在 venv 中运行
- `C:\ffmpeg\bin` 必须在 PATH 中
- 依赖方：`backend/requirements.txt`

### 4. 数据库连接池

`db_service.py` 使用 `Queue` 实现的连接池（默认 8 连接）。Flask `@teardown_request` 自动归还。**不要在请求外持有连接**。

### 5. 前后端通信

前端 Axios `baseURL: http://127.0.0.1:5000`。SSR 不适用，纯 SPA 架构。

## 容易踩坑的地方

- **ODBC 驱动**：必须安装 ODBC Driver 17 for SQL Server，连接信息在 `db_service.py` 第 26-34 行
- **Ollama**：需提前 `ollama pull qwen3:8b` 并启动服务
- **FunASR 首次加载慢**：首次调用需下载模型到本地缓存，约 1-2 分钟
- **`servers.txt` / `tickets.txt`**：UTF-16LE 编码的旧 Mock 数据，不要随意修改编码
- **LLM 输出必须是纯 JSON**：`ollama_service.py` 中 `parse_intent()` 有严格的 JSON 提取逻辑，修改 prompt 时保持 JSON 输出要求
- **前端 lint**：使用 oxlint + eslint，提交前运行 `npm run lint`

## 关键文件索引

| 文件 | 用途 |
|---|---|
| `backend/app.py` | Flask 主入口，所有路由 + 意图执行引擎 |
| `backend/chat_state.py` | 对话状态机 |
| `backend/ollama_service.py` | LLM 调用 + 意图解析 + 结果润色 |
| `backend/db_service.py` | 数据库连接池 + 全部 CRUD |
| `backend/asr_service.py` / `tts_service.py` | 语音识别 / 合成 |
| `frontend/src/App.vue` | 根组件：浮窗助手 + VAD 持续聆听 |
| `frontend/src/router/index.ts` | 8 页面 + 2 子布局路由 |
| `docs/PROMPT.md` | LLM Prompt 设计文档 |

## 测试文档

- [模型完整测试用例](./backend/模型完整测试用例.md) — 17 大类 API 测试
- [语音交互完整测试用例](./backend/语音交互完整测试用例.md)
- [工单参数配置新增卡片测试用例](./backend/工单参数配置新增卡片测试用例.md)
