"""
Ollama 服务模块：调用本地 Ollama 模型理解用户意图
"""
import requests
import json
import datetime

# Ollama 配置
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:8b"

# ========== 核心 System Prompt ==========
# 规则：严格 JSON 输出，绝不允许多余文字
# 占位符 {{CURRENT_DATE}} 会在调用时替换为今天的实际日期，
# 让 LLM 知道"最近一周/本月"对应的具体起止日期。

SYSTEM_PROMPT = (
    "意图解析器。你只能输出一行 JSON。\n"
    "\n"
    "intent 可选值: navigate / query / query_monitor / staff_query / schedule_query / operate / delete / summary / search / greeting / unknown\n"
    "\n"
    "【关键识别规则 — 优先级最高，必须遵守】\n"
    "1) 日期+序号工单查询：凡是用户说「查看/看 + 日期 + 的第N个工单」，intent 必须是 query、api 必须是 tickets_detail。\n"
    "   日期可以是阿拉伯数字（2026年7月27日）或中文数字（二零二六年七月二十七日）或仅月日（7月27日、七月二十七日）。\n"
    "   你必须把日期转换成 YYYYMMDD 格式，序号 N 转成数字，拼接为 TKT-YYYYMMDD-XXXX（4位补零）。\n"
    "   这是工单详情查询，绝对 不能 输出 search 意图！params 里 不能 有 assignee！\n"
    "2) 人员+数量统计：当用户说「XX 有多少 YY 的工单」时，必须输出 search 意图 + tickets_search。\n"
    "   这不是全局统计（tickets_stat），因为用户明确指定了某个人。params 里必须包含 assignee。\n"
    "   示例：张伟有多少高优先级的工单 → search，params={assignee:张伟, priority:高}\n"
    "3) 总结/报告：凡用户说「总结XX趋势」或类似，intent 必须是 summary + tickets_report，并推算正确的起止日期。\n"
    "4) 排班查询：凡用户说「XX日/某年某月某日的（早班/下午班/晚班）排班情况」或「今日值班/当前在线/本月排班次」，intent 必须是 schedule_query。\n"
    "   日期可以是阿拉伯数字或中文数字。班次类型（早班/下午班/晚班）可选，不指定则查全部。\n"
    "   今日值班 → schedule_query + schedule_today，当前在线 → schedule_query + schedule_online，本月排班次 → schedule_query + schedule_month_stats\n"
    "   params 中的 date 用 YYYY-MM-DD 格式。\n"
    "5) 排班操作：凡用户说「让XX排某日的早班/下午班/晚班」，intent 必须是 operate、api 必须是 schedule_assign。\n"
    "   日期同样支持阿拉伯数字和中文数字，params 包含 staff_name、shift_date、shift_type。\n"
    "   shift_type 必须是「早班」「下午班」「晚班」「休息」之一。\n"
    "6) 上下文连续问答：当用户说「其中有多少XX」「里面有多少XX」等指代词时，必须从【上下文提示】中复制上一轮的实际条件值。\n"
    "   关键规则：\n"
    "   - 如果【上下文提示】中有 start_date 和 end_date，必须将它们的实际值（如2026-07-07）复制到 params 中，不能用YYYY-MM-DD占位符。\n"
    "   - 如果【上下文提示】中有 status，也复制到 params。如果上一轮没有 status（如查的是'所有工单'），则不要加 status。\n"
    "   - 只追加用户新提出的条件（如 priority=高）。\n"
    "   例如上一轮查了'最近一周未完成工单'，上下文提示含 start_date=2026-07-07, end_date=2026-08-06, status=未完成，用户问'其中有多少高优先级的'，应输出 tickets_stat + status=未完成 + priority=高 + start_date=2026-07-07 + end_date=2026-08-06。\n"
    "   例如上一轮查了'最近一个月有多少工单'（无status），上下文提示含 start_date=2026-07-07, end_date=2026-08-06，用户问'其中有多少高优先级的'，应输出 tickets_stat + priority=高 + start_date=2026-07-07 + end_date=2026-08-06（不加status）。\n"
    "\n"
    "示例（严格按此格式，不要任何额外文字）：\n"
    '  打开监控 -> {"intent":"navigate","api":"navigate","params":{"target":"/monitor"}}\n'
    '  打开工单列表 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets"}}\n'
    '  跳转到工单列表 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets"}}\n'
    '  打开统计看板 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets/stats"}}\n'
    '  打开配置页 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets/config"}}\n'
    '  打开人员管理 -> {"intent":"navigate","api":"navigate","params":{"target":"/staff"}}\n'
    '  查看人员列表 -> {"intent":"navigate","api":"navigate","params":{"target":"/staff"}}\n'
    '  排班管理 -> {"intent":"navigate","api":"navigate","params":{"target":"/staff/schedule"}}\n'
    '  角色配置 -> {"intent":"navigate","api":"navigate","params":{"target":"/staff/roles"}}\n'
    '  回到首页 -> {"intent":"navigate","api":"navigate","params":{"target":"/"}}\n'
    '  查看工单5 -> {"intent":"query","api":"tickets_detail","params":{"id":5}}\n'
    '  查看2026年7月27日的第一个工单 -> {"intent":"query","api":"tickets_detail","params":{"id":"TKT-20260727-0001"}}\n'
    '  查看二零二六年七月二十七日的第一个工单 -> {"intent":"query","api":"tickets_detail","params":{"id":"TKT-20260727-0001"}}\n'
    '  查看七月二十七日的第三个工单 -> {"intent":"query","api":"tickets_detail","params":{"id":"TKT-20260727-0003"}}\n'
    '  查看7月28日的第三个工单 -> {"intent":"query","api":"tickets_detail","params":{"id":"TKT-20260728-0003"}}\n'
    '  看七月二十八日的第二个工单 -> {"intent":"query","api":"tickets_detail","params":{"id":"TKT-20260728-0002"}}\n'
    '  查看今天的第五个工单 -> {"intent":"query","api":"tickets_detail","params":{"id":"TKT-YYYYMMDD-0005"}}\n'
    '  看昨天第三个工单 -> {"intent":"query","api":"tickets_detail","params":{"id":"TKT-YYYYMMDD-0003"}}\n'
    '  有多少未完成的工单 -> {"intent":"query","api":"tickets_stat","params":{"status":"未完成"}}\n'
    '  有多少高优先级的工单 -> {"intent":"query","api":"tickets_stat","params":{"priority":"高"}}\n'
    '  有多少中优先级的工单 -> {"intent":"query","api":"tickets_stat","params":{"priority":"中"}}\n'
    '  其中有多少高优先级的 -> {"intent":"query","api":"tickets_stat","params":{"priority":"高","start_date":"<上下文实际值>","end_date":"<上下文实际值>"}} （如有上轮status也加上）\n'
    '  里面有多少中优先级的 -> {"intent":"query","api":"tickets_stat","params":{"priority":"中","start_date":"<上下文实际值>","end_date":"<上下文实际值>"}} （如有上轮status也加上）\n'
    '  有多少工单 -> {"intent":"query","api":"tickets_stat","params":{}}\n'
    '  有多少运维人员 -> {"intent":"staff_query","api":"staff_count","params":{}}\n'
    '  查人员数量 -> {"intent":"staff_query","api":"staff_count","params":{}}\n'
    '  最近一周完成了多少 -> {"intent":"query","api":"tickets_stat","params":{"status":"已完成","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  最近一周有多少已完成工单 -> {"intent":"query","api":"tickets_stat","params":{"status":"已完成","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  上周有多少未完成工单 -> {"intent":"query","api":"tickets_stat","params":{"status":"未完成","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  最近一个月有多少进行中工单 -> {"intent":"query","api":"tickets_stat","params":{"status":"进行中","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  7月27日有几个工单 -> {"intent":"query","api":"tickets_stat","params":{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  7月31日一共有几个工单 -> {"intent":"query","api":"tickets_stat","params":{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  7月27日有多少已完成工单 -> {"intent":"query","api":"tickets_stat","params":{"status":"已完成","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  你好 -> {"intent":"greeting","params":{}}\n'
    '  张伟有多少高优先级的工单 -> {"intent":"search","api":"tickets_search","params":{"assignee":"张伟","priority":"高"}}\n'
    '  王强有多少未完成的工单 -> {"intent":"search","api":"tickets_search","params":{"assignee":"王强","status":"未完成"}}\n'
    '  李娜有多少工单 -> {"intent":"search","api":"tickets_search","params":{"assignee":"李娜"}}\n'
    '  查张三名下未完成的高优先级工单 -> {"intent":"search","api":"tickets_search","params":{"assignee":"张三","status":"未完成","priority":"高"}}\n'
    '  查数据库相关的工单 -> {"intent":"search","api":"tickets_search","params":{"keyword":"数据库"}}\n'
    '  CPU 使用率 -> {"intent":"query_monitor","api":"monitor_latest","params":{"target":"cpu"}}\n'
    '  关闭工单1024 -> {"intent":"operate","api":"tickets_update","params":{"id":1024,"status":"已完成"}}\n'
    '  删除工单8 -> {"intent":"delete","api":"tickets_delete","params":{"id":8}}\n'
    '  把工单5指派给李四 -> {"intent":"operate","api":"tickets_assign","params":{"id":5,"assignee":"李四"}}\n'
    '  工单3转给张三 -> {"intent":"operate","api":"tickets_assign","params":{"id":3,"assignee":"张三"}}\n'
    '  总结本月趋势 -> {"intent":"summary","api":"tickets_report","params":{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  总结这周工单趋势 -> {"intent":"summary","api":"tickets_report","params":{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  总结本周工单趋势 -> {"intent":"summary","api":"tickets_report","params":{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}\n'
    '  今日值班 -> {"intent":"schedule_query","api":"schedule_today","params":{}}\n'
    '  当前在线 -> {"intent":"schedule_query","api":"schedule_online","params":{}}\n'
    '  本月排班次 -> {"intent":"schedule_query","api":"schedule_month_stats","params":{}}\n'
    '  2026年7月23日的早班排班情况 -> {"intent":"schedule_query","api":"schedule_detail","params":{"date":"2026-07-23","shift_type":"早班"}}\n'
    '  二零二六年七月二十三日的排班情况 -> {"intent":"schedule_query","api":"schedule_detail","params":{"date":"2026-07-23"}}\n'
    '  7月23日下午班排班情况 -> {"intent":"schedule_query","api":"schedule_detail","params":{"date":"2026-07-23","shift_type":"下午班"}}\n'
    '  让王强排7月23日的早班 -> {"intent":"operate","api":"schedule_assign","params":{"staff_name":"王强","shift_date":"2026-07-23","shift_type":"早班"}}\n'
    '  让李娜排二零二六年七月二十四日的晚班 -> {"intent":"operate","api":"schedule_assign","params":{"staff_name":"李娜","shift_date":"2026-07-24","shift_type":"晚班"}}\n'
    "\n"
    "中文数字日期转换规则（必须掌握）：\n"
    "- 年份：二零二六 = 2026（逐位转换：零→0, 一→1, 二→2, 三→3, 四→4, 五→5, 六→6, 七→7, 八→8, 九→9）\n"
    "- 月份/日期：七→7, 二十七→27（十位制：十一→11, 二十→20, 二十七→27, 三十一→31）\n"
    "- 序号：第一个→1, 第三→3, 第五→5（中文数字直接转阿拉伯数字）\n"
    "- 混合识别：同时支持阿拉伯数字和中文数字，如「2026年7月27日」和「二零二六年七月二十七日」都需正确转换成 TKT-YYYYMMDD-XXXX 格式\n"
    "- 序数词识别：第一个、第二个、第三个 → 1、2、3\n"
    "\n"
    "规则：\n"
    "1) 输出必须是纯 JSON 一行，不要 ``` 标记，不要解释。\n"
    "2) 只包含用户实际提到的参数，不要臆造。\n"
    "3) target 必须是路由路径，如 /tickets、/monitor、/。\n"
    "4) 当前日期是 {{CURRENT_DATE}}。\n"
    "5) 关于人员的数量问题（谁能有多少工单），必须用 search 意图，params 中包含 assignee=人名和对应筛选条件。\n"
    "6) 绝对不要在有日期+序号格式的句子中使用 search 或 assignee 参数。\n"
    "\n"
    "时间规则（根据当前日期计算具体日期）：\n"
    "- 今天 -> end_date = {{CURRENT_DATE}}\n"
    "- 最近N天 -> start_date = 今天往前N天, end_date = 今天\n"
    "- 最近一周 -> start_date = 今天往前7天, end_date = 今天\n"
    "- 上周 -> start_date = 上周一, end_date = 上周日\n"
    "- 这周/本周 -> start_date = 本周一, end_date = 今天\n"
    "- 最近一个月 -> start_date = 今天往前30天, end_date = 今天\n"
    "- 本月 -> start_date = 本月1日, end_date = 今天\n"
    "- 上月 -> start_date = 上月1日, end_date = 上月最后一天\n"
    "- X月份 -> start_date = X月1日, end_date = X月最后一天\n"
    "- X月X日/某月某日 -> start_date = end_date = 该日期（年取当前年）\n"
)

# 数据润色 Prompt（用于把 API 返回的 JSON 数据变成自然语言）
POLISH_PROMPT = (
    "你是轻言OPS 运维助手。基于统计数据，用自然、简洁的中文一句话回答用户。\n"
    "不要说「根据数据」这类废话，直接说结论。\n"
    "⚠️ 所有数字（日期、数量、百分比）一律使用阿拉伯数字，禁止输出中文数字（如「两千零二十」→必须输出「2020」）。\n"
    "格式示例：\n"
    "  工单：「共有50个工单，已完成16个、进行中15个、未完成19个」\n"
    "  监控：「当前 CPU 67.3%，内存 72.5%，磁盘 55.8%，网络上行 89 Mbps、下行 125 Mbps」\n"
)


# 多条件搜索结果润色（专用于 search 意图的"语音播报"）
SEARCH_PROMPT = (
    "你是轻言OPS 运维助手。请基于用户问题和搜索结果，用 1-2 句中文自然语言回复。\n"
    "要求：\n"
    "  1) 必须告诉用户：找到了多少条、按哪些条件筛的、前 1-3 条最相关工单的标题与编号。\n"
    "  2) 如果命中 0 条 → 明确说『没找到符合条件的工单』，并建议放宽条件。\n"
    "  3) 不要说『根据数据』这种废话；用第二人称；不要 Markdown；不要 JSON。\n"
    "  4) 不要编造数据，所有数字必须来自【搜索结果】。\n"
)


def understand_intent(user_input: str, context_str: str = "") -> dict:
    """
    调用 Ollama 理解用户意图，返回结构化 JSON

    Args:
        user_input: 用户输入文本
        context_str: 对话上下文字符串（由 ChatContext.to_prompt_context() 生成）

    策略：纯 LLM — 所有意图解析都通过大模型输出，不再使用规则匹配。
    SYSTEM_PROMPT 中已包含日期+序号、相对日期等典型场景的示例，
    LLM 应能直接产出 TKT-YYYYMMDD-XXXX 格式的工单 ID。
    """
    import datetime as _dt
    today_str = _dt.datetime.now().strftime("%Y-%m-%d")
    system_prompt_filled = SYSTEM_PROMPT.replace("{{CURRENT_DATE}}", today_str)

    # 1. 构建上下文（限制总长度，避免 exceed context window）
    context = ""
    if context_str:
        max_context_chars = 400  # 上下文最多 400 字符，保证 prompt 不超标
        ctx = context_str
        if len(ctx) > max_context_chars:
            # 从头截断（保留最新的对话）
            ctx = "...(早期对话已省略)\n" + ctx[-(max_context_chars - 30):]
        context = ctx + "\n【当前提问】\n"

    full_prompt = f"{system_prompt_filled}\n\n{context}用户说：{user_input}\n\n请输出 JSON："

    result = call_ollama_raw(full_prompt, temperature=0.1, max_tokens=500)
    print(f"[意图] LLM 原始返回({len(result)}字符): {result[:120]}")

    intent_data = _parse_llm_json(result)

    # 2. 降级：模型返回空或格式错误 → 不带上下文重试一次
    if intent_data.get("intent") == "error":
        error_msg = intent_data.get("message", "")
        if "空内容" in error_msg or "格式错误" in error_msg:
            print(f"[意图] ⚠️ 带上下文失败({error_msg[:30]})，尝试无上下文重试...")
            retry_prompt = f"{system_prompt_filled}\n\n用户说：{user_input}\n\n请输出 JSON："
            result2 = call_ollama_raw(retry_prompt, temperature=0.1, max_tokens=500)
            intent_data = _parse_llm_json(result2)
            if intent_data.get("intent") not in ("error", "unknown"):
                return intent_data

    # 3. 失败兜底：直接返回错误，不使用规则匹配
    if intent_data.get("intent") in ("error", "unknown"):
        print(f"[意图] ⚠️ LLM 无法解析，返回原始结果: {intent_data}")

    return intent_data


# 合法 intent 值集合
_VALID_INTENTS = {"navigate", "query", "query_monitor", "staff_query", "schedule_query", "operate", "delete", "summary", "search", "greeting", "unknown"}

def _clean_intent(intent: str) -> str:
    """清理 intent 字段：去除管道符、空格，取第一个合法值"""
    if not intent:
        return "unknown"
    # 如果包含管道符，取第一个合法部分
    parts = intent.replace(" ", "").split("|")
    for p in parts:
        p = p.strip()
        if p in _VALID_INTENTS:
            return p
    return "unknown"


def _parse_llm_json(text: str) -> dict:
    """解析 LLM 返回的 JSON，处理空返回、截断、代码块等异常格式"""
    if not text:
        return {"intent": "error", "message": "模型返回空内容"}
    result = text.strip()

    # 去掉 markdown 代码块：```json ... ``` 或 ``` ... ```
    if result.startswith("```"):
        end_idx = result.find("```", 3)
        if end_idx > 0:
            result = result[3:end_idx].strip()
            if result.startswith("json"):
                result = result[4:].strip()
        else:
            result = result[3:].strip()

    try:
        data = json.loads(result)
        data["intent"] = _clean_intent(data.get("intent", "unknown"))
        return data
    except json.JSONDecodeError:
        pass

    # 栈法：从最外层 { 到对应的 }
    stack = []
    start = -1
    for i, ch in enumerate(result):
        if ch == '{':
            if not stack:
                start = i
            stack.append(ch)
        elif ch == '}':
            if stack:
                stack.pop()
                if not stack and start >= 0:
                    candidate = result[start:i+1]
                    try:
                        data = json.loads(candidate)
                        data["intent"] = _clean_intent(data.get("intent", "unknown"))
                        return data
                    except:
                        pass

    # 栈法失败 — 检查是否是截断的 JSON（{ 比 } 多）
    open_count = result.count("{")
    close_count = result.count("}")
    if open_count > close_count:
        # 尝试补全截断的 JSON
        missing = open_count - close_count
        truncated = result + ("}" * missing)
        try:
            data = json.loads(truncated)
            data["intent"] = _clean_intent(data.get("intent", "unknown"))
            print(f"[意图] ⚠️ JSON 截断已补全 (补了 {missing} 个 }})")
            return data
        except json.JSONDecodeError:
            pass

    # 兜底正则
    import re
    match = re.search(r'\{[^{}]*\}', result)
    if match:
        try:
            data = json.loads(match.group())
            data["intent"] = _clean_intent(data.get("intent", "unknown"))
            return data
        except:
            pass
    return {"intent": "error", "message": f"模型返回格式错误: {text[:100]}"}


# ========== 中文数字转换 ==========
# 映射表：中文数字 → 整数，支持常见的序数表达式
_CN_NUM_MAP = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

def _cn_num_to_int(cn: str) -> int | None:
    """
    将中文数字或阿拉伯数字转为整数。
    支持：一→1, 十→10, 十一→11, 二十→20, 二十三→23, 1→1
    不支持百以上（工单序号通常不会超过 99）
    """
    if not cn:
        return None
    # 1) 阿拉伯数字直接转
    try:
        return int(cn)
    except ValueError:
        pass

    # 2) 单个中文数字
    if len(cn) == 1:
        return _CN_NUM_MAP.get(cn)

    # 3) "十" 开头（十一 ~ 十九）
    if cn == "十":
        return 10
    if cn.startswith("十"):
        unit = _CN_NUM_MAP.get(cn[1:])
        if unit is not None:
            return 10 + unit
        return None

    # 4) "X十" 结尾（二十、三十...九十）
    if cn.endswith("十") and len(cn) == 2:
        tens = _CN_NUM_MAP.get(cn[0])
        if tens is not None:
            return tens * 10
        return None

    # 5) "X十Y" 格式（二十三、九十九）
    if len(cn) == 3 and cn[1] == "十":
        tens = _CN_NUM_MAP.get(cn[0])
        units = _CN_NUM_MAP.get(cn[2])
        if tens is not None and units is not None:
            return tens * 10 + units
        return None

    return None


def _rule_based_navigate(user_input: str) -> dict | None:
    """
    规则降级：当 Ollama 不可用时，用关键词匹配处理常见导航指令和工单操作
    返回 None 表示无法匹配
    """
    text = user_input.strip().replace("。", "").replace("，", "")
    
    import re
    import datetime as _dt
    
    # ===== 日期+序号工单查询（如：查看2026年7月27日的第一个工单）=====
    # 模式 A：X年X月X日的第N个工单（年份可选，省略则用当前年）
    dm = re.search(
        r'(?:查看|查|看)\s*'
        r'(?:(\d{4})\s*年\s*)?'          # 年份（可选）
        r'(\d{1,2})\s*月\s*'
        r'(\d{1,2})\s*日'
        r'(?:的)?\s*'
        r'第\s*([一二三四五六七八九十\d]+)\s*个'
        r'(?:\s*工单)?',
        text
    )
    if dm:
        year = dm.group(1) or str(_dt.datetime.now().year)
        month = dm.group(2).zfill(2)
        day = dm.group(3).zfill(2)
        seq = _cn_num_to_int(dm.group(4))
        if seq is not None:
            tid = f"TKT-{year}{month}{day}-{seq:04d}"
            return {"intent": "query", "api": "tickets_detail", "params": {"id": tid}}
    
    # 模式 B：今天/昨天/前天的第N个工单
    dm = re.search(
        r'(?:查看|查|看)\s*'
        r'(今天|昨天|前天)'
        r'(?:的)?\s*'
        r'第\s*([一二三四五六七八九十\d]+)\s*个'
        r'(?:\s*工单)?',
        text
    )
    if dm:
        day_word = dm.group(1)
        seq = _cn_num_to_int(dm.group(2))
        if seq is not None:
            today = _dt.datetime.now()
            delta = {"昨天": 1, "前天": 2}.get(day_word, 0)
            target = today - _dt.timedelta(days=delta)
            tid = f"TKT-{target.strftime('%Y%m%d')}-{seq:04d}"
            return {"intent": "query", "api": "tickets_detail", "params": {"id": tid}}
    
    # --- 工单操作兜底 ---
    # 查看工单N / 查工单N（支持数字和 TKT-YYYYMMDD-XXXX 格式）
    m = re.search(r'(?:查看|查|看)\s*(?:工单|订单)?\s*(\d+|TKT-\d{8}-\d{4,})', text)
    if m:
        tid = m.group(1)
        return {"intent": "query", "api": "tickets_detail", "params": {"id": tid}}
    
    # 关闭工单N
    m = re.search(r'关闭\s*(?:工单|订单)?\s*(\d+|TKT-\d{8}-\d{4,})', text)
    if m:
        return {"intent": "operate", "api": "tickets_update", "params": {"id": m.group(1), "status": "已完成"}}
    
    # 删除工单N
    m = re.search(r'删除\s*(?:工单|订单)?\s*(\d+|TKT-\d{8}-\d{4,})', text)
    if m:
        return {"intent": "delete", "api": "tickets_delete", "params": {"id": m.group(1)}}
    
    # 指派工单N给XXX / 工单N转给XXX
    m = re.search(r'(?:把\s*)?工单\s*(\d+|TKT-\d{8}-\d{4,})\s*(?:指派给|转给|分给)\s*(\S+)', text)
    if m:
        return {"intent": "operate", "api": "tickets_assign", "params": {"id": m.group(1), "assignee": m.group(2)}}
    
    # 总结趋势
    for kw in ["总结", "趋势", "报告"]:
        if kw in text:
            import datetime as _dt
            today = _dt.datetime.now()
            thirty_ago = (today - _dt.timedelta(days=30))
            return {"intent": "summary", "api": "tickets_report",
                    "params": {"start_date": thirty_ago.strftime("%Y-%m-%d"), "end_date": today.strftime("%Y-%m-%d")}}

    # --- 排班查询兜底 ---
    # 今日值班
    if "今日值班" in text or "今天值班" in text:
        return {"intent": "schedule_query", "api": "schedule_today", "params": {}}
    # 当前在线
    if "当前在线" in text or "在线人数" in text:
        return {"intent": "schedule_query", "api": "schedule_online", "params": {}}
    # 本月排班
    if "本月排班" in text or "排班统计" in text:
        return {"intent": "schedule_query", "api": "schedule_month_stats", "params": {}}
    # X月X日（XX班）排班情况
    dm = re.search(
        r'(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日'
        r'(?:的)?\s*(早班|下午班|晚班)?\s*(?:排班|值班|情况)',
        text
    )
    if dm:
        year = dm.group(1) or str(_dt.datetime.now().year)
        month = dm.group(2).zfill(2)
        day = dm.group(3).zfill(2)
        shift = dm.group(4) or None
        params = {"date": f"{year}-{month}-{day}"}
        if shift:
            params["shift_type"] = shift
        return {"intent": "schedule_query", "api": "schedule_detail", "params": params}
    # 让XX排某日的班次
    dm = re.search(
        r'让\s*(\S+?)\s*排\s*'
        r'(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日'
        r'(?:的)?\s*(早班|下午班|晚班|休息)',
        text
    )
    if dm:
        staff = dm.group(1)
        year = dm.group(2) or str(_dt.datetime.now().year)
        month = dm.group(3).zfill(2)
        day = dm.group(4).zfill(2)
        shift = dm.group(5)
        return {"intent": "operate", "api": "schedule_assign",
                "params": {"staff_name": staff, "shift_date": f"{year}-{month}-{day}", "shift_type": shift}}
    
    # 查X名下/未完成/高优先级的工单
    if "查" in text and ("名下" in text or "搜索" in text or
                          any(kw in text for kw in ["未完成", "高优先", "工单"])):
        search_params = {}
        m2 = re.search(r'查\s*(\S+?)(?:名下|的)', text)
        if m2:
            search_params["assignee"] = m2.group(1)
        if "未完成" in text:
            search_params["status"] = "未完成"
        if "高优先" in text:
            search_params["priority"] = "高"
        if "中优先" in text:
            search_params["priority"] = "中"
        if search_params:
            return {"intent": "search", "api": "tickets_search", "params": search_params}
    
    # --- 导航兜底 ---
    nav_map = [
        (["跳转到工单列表", "打开工单列表", "工单列表", "进入工单列表", "看工单"], "/tickets"),
        (["跳转到首页", "打开首页", "回到首页", "首页", "主页", "返回首页"], "/"),
        (["跳转到监控", "打开监控", "监控大盘", "打开监控大盘", "看监控"], "/monitor"),
        (["工单统计", "统计看板", "工单看板", "打开统计"], "/tickets/stats"),
        (["工单配置", "参数配置", "打开配置"], "/tickets/config"),
    ]
    for keywords, target in nav_map:
        for kw in keywords:
            if kw in text:
                return {"intent": "navigate", "api": "navigate", "params": {"target": target}}
    return None


def summarize_data(user_question: str, api_data: dict) -> str:
    """
    数据润色：把 API 返回的 JSON 数据变成自然语言回复
    
    Args:
        user_question: 用户原始问题
        api_data: API 返回的统计数据
    """
    # === 直出模式 1：简单状态计数查询 ===
    # 当 api_data 是 {"total": N, "status": "X"} 格式时，直接生成回复
    # 绕过 LLM 避免幻觉（LLM 经常把 23 编成 17）
    status = api_data.get("status", "")
    total = api_data.get("total")
    if status and total is not None:
        return f"共有{total}个{status}工单。"

    # === 直出模式 2：全量统计（含各状态分布）===
    # 当 api_data 是 get_tickets_stat() 的返回值时
    if "status_distribution" in api_data:
        sd = api_data.get("status_distribution", {})
        total = api_data.get("total", 0)
        done = sd.get("已完成", 0)
        pending = sd.get("未完成", 0)
        progress = sd.get("进行中", 0)
        parts = [f"总共{total}个工单"]
        if done: parts.append(f"已完成{done}个")
        if progress: parts.append(f"进行中{progress}个")
        if pending: parts.append(f"未完成{pending}个")
        return "，".join(parts) + "。"

    # === 兜底：走 LLM 润色 ===
    prompt = (
        f"{POLISH_PROMPT}\n\n"
        f"用户的问题是：「{user_question}」\n"
        f"查到的数据：{json.dumps(api_data, ensure_ascii=False, default=str)}\n"
        f"请用一句话总结回复用户："
    )
    result = call_ollama_raw(prompt, temperature=0.3, max_tokens=500)
    return result.strip() or "查询完成，数据已获取。"


def polish_search_result(user_question: str, search_data: dict) -> str:
    """
    把多条件搜索结果润色为语音播报文案（search 意图专用）
    Args:
        user_question: 用户原始问题（如"查张三名下未完成的高优先级工单"）
        search_data: db_service.search_tickets_dynamic 返回的字典
            {"tickets":[...], "total":N, "applied_filters":{...}}
    """
    if not isinstance(search_data, dict):
        search_data = {}
    tickets = search_data.get("tickets", [])
    total = search_data.get("total", len(tickets))
    applied = search_data.get("applied_filters", {})

    # 0 条命中：跳过 LLM，直接硬编码（避免 LLM 误编）
    if total == 0:
        # 友好地告诉用户筛选条件
        cond = "、".join(f"{k}={v}" for k, v in applied.items()) or "当前条件"
        return f"没有找到符合条件的工单（{cond}），建议放宽关键词或时间范围后再试。"

    # 构建前3条工单标题的硬编码模板（LLM 失败时兜底）
    top = tickets[:3]
    top_titles = [f"「{t.get('title','')}」({t.get('id','')})" for t in top]
    hardcoded_prefix = f"已为您找到{total}条符合条件的工单，筛选条件是"
    cond_parts = []
    if applied.get("keyword"): cond_parts.append(f"关键词「{applied['keyword']}」")
    if applied.get("assignee"): cond_parts.append(f"负责人「{applied['assignee']}」")
    if applied.get("status"): cond_parts.append(f"状态「{applied['status']}」")
    if applied.get("priority"): cond_parts.append(f"优先级「{applied['priority']}」")
    hardcoded_prefix += "、".join(cond_parts) if cond_parts else "综合条件"
    hardcoded_prefix += "。"
    if top_titles:
        hardcoded_prefix += f"前{len(top_titles)}条最相关的工单：{'，'.join(top_titles)}。"

    # 命中则交给 LLM 润色
    summary = {
        "total": total,
        "applied_filters": applied,
        "top": top,
    }
    prompt = (
        f"{SEARCH_PROMPT}\n\n"
        f"用户的问题是：「{user_question}」\n"
        f"【搜索结果】\n{json.dumps(summary, ensure_ascii=False, indent=2, default=str)}\n\n"
        f"请开始你的回复："
    )
    result = call_ollama_raw(prompt, temperature=0.3, max_tokens=200)
    llm_reply = result.strip() if result else ""

    # 如果 LLM 返回空或太短（<15字），直接用硬编码版本
    if not llm_reply or len(llm_reply) < 15:
        return hardcoded_prefix

    # 检查 LLM 回复是否包含工单标题信息
    has_title = any(t.get("title", "") and t["title"] in llm_reply for t in top[:3])
    if not has_title and top_titles:
        # LLM 遗漏了标题，补充到回复末尾
        return llm_reply + f"前{len(top_titles)}条最相关的工单：{'，'.join(top_titles)}。"

    return llm_reply


# ========== 趋势报告 Prompt（summary 专用 — 只让 LLM 做趋势分析，不说基础数字）==========
REPORT_PROMPT = (
    "你是轻言OPS 运维助手。基于下方工单趋势数据，用 1-2 句中文总结趋势特征。\n"
    "只需要说：趋势方向（上升/下降/平稳）、高频问题类型、简要建议。\n"
    "不要说日期、天数、总量、完成率 —— 这些系统已自动生成。\n"
    "不要 Markdown、不要说「根据数据」。\n"
    "⚠️ 所有数字一律使用阿拉伯数字，禁止输出中文数字。\n"
)


def summarize_report(user_question: str, report_data: dict) -> str:
    """
    趋势总结：基础数字由代码拼接（保证正确），LLM 只负责趋势分析。
    """
    if not isinstance(report_data, dict):
        return "暂无可汇总数据。"

    total = report_data.get("total", 0)
    flt = report_data.get("filter", {})
    start = flt.get("start_date", "?")
    end   = flt.get("end_date", "?")
    days  = flt.get("days", 0)

    # ★ 调试：打印接收到的 filter 数据
    print(f"[summary] DEBUG filter={flt}  total={total}  days={days}")

    if total == 0:
        return f"{start} 至 {end} 期间无新增工单。"

    # ---- 基础数据（代码直拼，0 幻觉风险）----
    sd = report_data.get("status_distribution", {})
    done = sd.get("已完成", 0)
    progress = sd.get("进行中", 0)
    pending = sd.get("未完成", 0)
    rate = (report_data.get("completion_rate", 0) or 0) * 100
    avg_daily = round(total / days, 1) if days else total

    header = (
        f"{start} 至 {end} 共 {days} 天，新增工单 {total} 个，日均有 {avg_daily} 个。"
        f"已完成 {done} 个，进行中 {progress} 个，未完成 {pending} 个，完成率 {rate:.1f}%。"
    )

    # ---- LLM 趋势分析 ----
    td = report_data.get("type_distribution", {})
    daily = report_data.get("status_by_day", [])
    analysis_data = {
        "高频类型": {k: v for k, v in td.items() if v > 0},
        "每日新增": [{"日期": d.get("date"), "新增": sum(d.get(k, 0) for k in ("未完成", "进行中", "已完成"))} for d in daily[:14]],
    }

    prompt = (
        f"{REPORT_PROMPT}\n\n"
        f"【数据】\n{json.dumps(analysis_data, ensure_ascii=False)}\n\n"
        f"回答："
    )
    result = call_ollama_raw(prompt, temperature=0.3, max_tokens=200)
    analysis = result.strip()
    print(f"[summary] LLM 分析结果(len={len(analysis)}): {analysis[:80]}")

    if analysis and len(analysis) >= 5:
        return header + analysis

    # ---- LLM 失败 → 数据兜底分析 ----
    print(f"[summary] LLM 分析失败，使用数据兜底")
    # 趋势方向
    trend_label = "平稳"
    if len(daily) >= 3:
        mid = len(daily) // 2
        first = sum(sum(d.get(k,0) for k in ("未完成","进行中","已完成")) for d in daily[:mid])
        second = sum(sum(d.get(k,0) for k in ("未完成","进行中","已完成")) for d in daily[mid:])
        if second > first * 1.3:
            trend_label = "上升"
        elif first > second * 1.3:
            trend_label = "下降"
    # 高频类别
    top = sorted([(k,v) for k,v in td.items() if k!="其他" and v>0], key=lambda x:x[1], reverse=True)[:2]
    parts = []
    if top:
        parts.append("高频问题集中在" + "、".join(f"{k}({v}个)" for k,v in top))
    parts.append(f"整体趋势{trend_label}")
    fallback = "。" + "，".join(parts) + "。"
    return header + fallback


def call_ollama_raw(prompt: str, temperature: float = 0.1, max_tokens: int = 200) -> str:
    """调用 Ollama 原始接口，带重试"""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }

    for attempt in range(1, 4):  # 最多重试 3 次
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            raw_response = data.get("response", "")
            text = raw_response.strip() if raw_response else ""
            if not text:
                done = data.get("done", False)
                done_reason = data.get("done_reason", "")
                eval_count = data.get("eval_count", 0)
                prompt_tokens = data.get("prompt_eval_count", 0)
                print(f"[Ollama] ⚠️ 模型返回空内容 (attempt={attempt}, done={done}, reason={done_reason}, eval={eval_count}, prompt_tokens={prompt_tokens})")
                if attempt < 3:
                    import time
                    time.sleep(0.8 * attempt)  # 递增等待
                    continue
            return text
        except requests.exceptions.ConnectionError:
            print(f"[Ollama] ❌ 无法连接到 Ollama (attempt={attempt})，请确认 ollama serve 已启动")
            if attempt < 3:
                import time
                time.sleep(1.5 * attempt)
                continue
            return ""
        except Exception as e:
            print(f"[Ollama] 调用失败 (attempt={attempt}): {e}")
            if attempt < 3:
                import time
                time.sleep(0.5 * attempt)
                continue
            return ""
    return ""
