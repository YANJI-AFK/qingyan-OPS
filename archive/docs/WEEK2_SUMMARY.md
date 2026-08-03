# 数字人智能助手 — 第二周开发总结

> 日期：2026-07-19 ~ 2026-07-20  
> 目标：LLM Prompt 工程、TTS 音频闭环、业务控制器、二次确认机制

---

## 一、本周新增架构

```
🎤 按住录音 → ffmpeg转WAV → 📝 FunASR(含VAD调优) → 🧠 Ollama(JSON输出)
                                                            ↓
🗂️ 上下文记忆(20轮) ← ⚡ execute_action 意图分发器 ← JSON 意图
        ↓                           ↓
  navigate 页面跳转    operate 二次确认 → 🔊 /api/tts → 浏览器播放
        ↓                           ↓
  query 工单/监控      确认/取消状态机 → 修改 TICKETS 数据
```

---

## 二、本周新增/修改文件

### 📦 生产代码

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/app.py` | 🔥 大量重构 | `/api/tts`、`/api/chat/reset`、`/api/tickets/<id>`、`/api/debug/pending`；`execute_action()` 意图分发器、`_handle_confirmation()` 确认流程；`chat_history` 上下文记忆、`pending_operation` 状态机；ASR 预加载；移除后端 SAPI 播放 |
| `backend/ollama_service.py` | 🔥 重写 | 全新 `SYSTEM_PROMPT`（5类意图+4条绝对规则）；`POLISH_PROMPT` 数据润色；`summarize_data()`；`understand_intent()` 支持历史上下文+JSON容错 |
| `backend/tts_service.py` | ➕ 新增 | `synthesize_to_wav()` — 文字→WAV字节流 |
| `backend/mock_data.py` | 🆕 新建 | 共享Mock数据（50条工单），消除 `app.py` 与 `integration_test.py` 数据不一致 |
| `backend/asr_service.py` | 🔧 调优 | `vad_kwargs`（静音截断800ms、噪声阈值0.6） |
| `frontend/src/App.vue` | 🔥 重写 | `playTTS()` 浏览器播放；`/chat` 响应处理（navigate跳转+TTS）；识别结果气泡显示；按住说话模式 |

### 📄 文档

| 文件 | 说明 |
|------|------|
| `docs/PROMPT.md` | 两个核心Prompt完整文档+测试用例+防坑记录 |

### 🧪 测试脚本（已移至 `tests/`）

| 文件 | 说明 |
|------|------|
| `tests/integration_test.py` | 全链路整合测试 |
| `tests/record_and_recognize.py` | 录音+识别裸测试 |
| `tests/test_asr.py` / `test_ollama.py` / `test_tts.py` | 各模块单元测试 |

---

## 三、本周解决的核心问题

### 1. ffmpeg 安装与 PATH 配置（Windows）

**现象**：`ffmpeg -version` 报 `CommandNotFoundException`，Flask reloader 子进程也找不到。

**解决**：winget 安装到 `C:\ffmpeg\bin\` → 临时 `$env:Path` + 永久 `[Environment]::SetEnvironmentVariable` → `app.py` 启动时注入 PATH → `subprocess.run` 使用绝对路径。

### 2. 前端录音交互模式选择

| 版本 | 方案 | 结果 |
|------|------|------|
| V1 | MediaRecorder 按住说话 | ✅ 简单可用 |
| V2 | Web Audio API + VAD 自动检测 | ❌ 交互不符预期，回退 |
| V3 | 恢复按住说话 + 前端播放TTS | ✅ 当前方案 |

### 3. 后端双播报（重音）

**现象**：后端 SAPI `speak_async()` + 前端 `/api/tts` → 每句话播两遍。

**解决**：移除后端所有 `speak_async()` 调用，TTS 统一由前端 `/api/tts` → `Audio.play()` 负责。

### 4. LLM JSON 输出不稳定

**现象**：LLM 偶尔在 JSON 外加文字，`json.loads()` 失败。

**解决**：Prompt 强调"只输出一行 JSON" + 正则 `re.search(r'\{[^{}]*\}', result)` 提取 + `temperature=0.1`。

### 5. navigate 跳转不生效

**现象**：LLM 返回正确 JSON，页面不跳转。

**解决**：前端解析 `/chat` 的 `action` + `target`，执行 `router.push(target)`。

### 6. Mock 数据不一致

**现象**：`integration_test.py` 5条工单 vs `app.py` 50条。

**解决**：提取 `mock_data.py`，两边统一 `from mock_data import TICKETS`。

### 7. 修改操作无实际效果

**现象**："确认"后系统回复已修改，但状态未变。

**排查**：添加 `[确认] ✅ 工单 x: 'old' → 'new'` 日志 + `/api/debug/pending` 接口 + `/api/tickets/<id>` 验证端点。

---

## 四、API 接口汇总（本周新增）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/transcribe` | 🆕 语音转写（音频→文字） |
| POST | `/api/tts` | 🆕 TTS 合成（文字→WAV流） |
| POST | `/api/chat/reset` | 🆕 重置对话历史 |
| GET | `/api/tickets/<id>` | 🆕 查看单个工单 |
| GET | `/api/debug/pending` | 🆕 查看待确认状态 |
| POST | `/chat` | 🔧 增强：上下文记忆、二次确认、数据润色、navigate跳转 |

---

## 五、LLM Prompt 体系

**System Prompt**（5种意图 + 4条绝对规则）→ JSON 控制器  
**Polish Prompt**（API数据 → 自然语言一句话）→ 回复润色

详见 `docs/PROMPT.md`

---

## 六、典型交互

### 查询工单
```
🎤 "查看工单五" → LLM: tickets_detail id=5
🔊 "工单5：修改密码失败，状态「未完成」，优先级高，负责人赵六。"
```

### 修改工单（二次确认）
```
🎤 "把工单3改成已完成"
🔊 "确定要将工单「数据库连接超时」改为「已完成」吗？"
🎤 "确认" → 🔊 "已更新为「已完成」。"
```

### 页面跳转
```
🎤 "打开监控" → 🔊 "正在跳转到监控大盘" → 页面自动切换
```

---

## 七、启动方式

```powershell
# 终端1：后端
cd backend && python app.py

# 终端2：前端
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`，按住 🎤 按钮说话即可。

---

## 八、下一步计划

- [ ] 前端浮动数字人窗口（对话气泡+历史记录）
- [ ] 打字机效果/逐字显示
- [ ] 接入真实数据库（SQLite）
- [ ] TTS 音色升级
- [ ] 断网全流程验收测试
