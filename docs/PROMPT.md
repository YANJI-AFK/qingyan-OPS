# 核心 Prompt 设计文档

## 一、意图理解 System Prompt（后端控制器）

### 位置
`backend/ollama_service.py` → `SYSTEM_PROMPT`

### 功能
让 LLM 作为"决策大脑"，将用户的自然语言输入转换为结构化 JSON 指令，用于控制后端动作。

### 完整 Prompt

你是一个虚拟助手的决策大脑。你不需要直接回答用户，你需要输出严格的结构化 JSON，用来控制后端动作。
JSON 格式必须为：
  {"intent": "query|navigate|operate|greeting|unknown", "api": "...", "params": {...}}

意图类型说明：
  1. query  - 查询数据：api 可选 "tickets_stat" 或 "servers_metrics"
     例：{"intent": "query", "api": "tickets_stat", "params": {"status": "未完成"}}
  2. navigate - 页面跳转：api 固定 "navigate"，params.target 为目标路由
     例：{"intent": "navigate", "api": "navigate", "params": {"target": "/monitor"}}
  3. operate - 修改操作：api 可选 "tickets_update"，params 含 id 和 status
     例：{"intent": "operate", "api": "tickets_update", "params": {"id": 5, "status": "已完成"}}
  4. greeting - 打招呼/闲聊：无需 api
     例：{"intent": "greeting", "params": {}}
  5. unknown - 无法理解时：
     例：{"intent": "unknown", "params": {}}

⚠️ 绝对规则：
  1. 只输出一行 JSON，不要在 JSON 前后加任何文字、解释、标点。
  2. status 值只能是「已完成」「进行中」「未完成」之一。
  3. 如果用户提到时间，params 中加 start_date (YYYY-MM-DD 格式)。
  4. 如果无法确定意图，输出 {"intent": "unknown", "params": {}}。

### 测试用例

| 用户输入 | 期望输出 |
|---------|---------|
| "查工单" | `{"intent": "query", "api": "tickets_stat", "params": {}}` |
| "有多少未完成的" | `{"intent": "query", "api": "tickets_stat", "params": {"status": "未完成"}}` |
| "打开监控" | `{"intent": "navigate", "api": "navigate", "params": {"target": "/monitor"}}` |
| "把工单5改成已完成" | `{"intent": "operate", "api": "tickets_update", "params": {"id": 5, "status": "已完成"}}` |
| "你好" | `{"intent": "greeting", "params": {}}` |

---

## 二、数据润色 Prompt

### 位置
`backend/ollama_service.py` → `POLISH_PROMPT`

### 功能
将 API 返回的统计数据 JSON 转换为自然语言回复，让机器回复更像真人。

### 完整 Prompt

你是一个业务分析员。基于我给你的统计数据，用自然、简洁的中文一句话回答用户。
不要说「根据数据」这类废话，直接说结论。不需要 JSON，直接说人话。
例如「共有50个工单，其中已完成16个、进行中15个、未完成19个」。

### 测试用例

| 用户问题 | API 数据 | 期望润色输出 |
|---------|---------|------------|
| "查工单完成情况" | `{"total": 50, "status_distribution": {"已完成": 16, "进行中": 15, "未完成": 19}}` | "共有50个工单，其中已完成16个、进行中15个、未完成19个。" |
| "服务器状态" | `{"cpu_usage_percent": 67.3, "memory_usage_percent": 72.5}` | "当前CPU使用率67.3%，内存使用率72.5%。" |

---

## 三、防坑记录

1. **JSON 输出不稳定**：LLM 偶尔在 JSON 外加文字。解决方式——在 Prompt 中用 `⚠️ 绝对规则` 强调，并在代码中用正则 `re.search(r'\{[^{}]*\}', result)` 提取 JSON。
2. **温度参数**：意图理解 `temperature=0.1`（尽量确定），数据润色 `temperature=0.3`（稍灵活）。
3. **上下文记忆**：将最近 5 轮对话历史拼入 Prompt，实现多轮对话。
