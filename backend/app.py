from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import re
import sys
import psutil

# ========== 环境检查：必须激活 venv 运行 ==========
_VENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venv")
_VENV_PYTHON = os.path.join(_VENV, "Scripts", "python.exe")
if not sys.executable.lower().startswith(_VENV.lower()):
    print("=" * 60)
    print("❌ 错误：未激活虚拟环境！")
    print()
    print("   请先在项目根目录激活虚拟环境再运行：")
    print(f"   cd {os.path.dirname(_VENV)}")
    print(f"   venv\\Scripts\\activate")
    print(f"   cd backend")
    print(f"   python app.py")
    print()
    print(f"   当前 Python: {sys.executable}")
    print(f"   期望 Python: {_VENV_PYTHON}")
    print("=" * 60)
    sys.exit(1)

# ========== 确保 ffmpeg 在 PATH 中（Flask reloader 子进程和 FunASR 内部都需要）==========
_FFMPEG_BIN = r"C:\ffmpeg\bin"
if os.path.isdir(_FFMPEG_BIN) and _FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_BIN + ";" + os.environ.get("PATH", "")
    print(f"[环境] 已将 {_FFMPEG_BIN} 加入 PATH")

import atexit
import ollama_service
import asr_service
import tts_service
import db_service
from chat_state import ChatState

# ========== 工单 ID 格式标准化（语音输入 → 标准格式）==========
def _normalize_ticket_id(raw_id):
    """
    将各种语音输入产生的工单 ID 格式统一为 TKT-YYYYMMDD-XXXX。
    支持的格式：
      - 纯数字编号 "5"                    → "5"（保持原样）
      - 无短横线 "TKT202608310005"         → "TKT-20260831-0005"
      - 无 TKT 前缀 "202608310005"         → "TKT-20260831-0005"
      - 标准格式 "TKT-20260831-0005"       → 保持不变（已正确）
    """
    if raw_id is None:
        return None
    if isinstance(raw_id, int):
        return str(raw_id)

    raw_id = str(raw_id).strip()

    # 已是标准格式：TKT-YYYY-MM-DD-XXXX
    if re.match(r'^TKT-\d{4}-\d{2}-\d{2}-\d{4}$', raw_id):
        return raw_id

    # 去掉 TKT 前缀（不区分大小写、有无横线）
    digits = raw_id.upper().replace("TKT-", "").replace("TKT", "")

    if not digits.isdigit():
        return raw_id  # 非纯数字（如简单编号），保持原样

    # 短数字如"5" → 直接返回
    if len(digits) <= 4:
        return digits

    # 12 位数字：YYYYMMDDXXXX → TKT-YYYYMMDD-XXXX
    if len(digits) == 12:
        return "TKT-{}-{}".format(digits[0:8], digits[8:12])

    # 超过 12 位数字（容错）→ 取前 12 位
    if len(digits) > 12:
        digits = digits[:12]
        return "TKT-{}-{}".format(digits[0:8], digits[8:12])

    return raw_id

# ========== 全局对话状态机 ==========
chat_state = ChatState()

app = Flask(__name__)
CORS(app)

# ========== 请求结束时自动归还数据库连接 ==========
@app.teardown_request
def _teardown_db(exception=None):
    """每个请求结束后，将借用的数据库连接归还到连接池"""
    db_service.return_connection()

# ========== 应用启动时初始化数据库（建表 + 迁移旧数据） ==========
try:
    db_service.init_database()
    print("[启动] 数据库初始化/迁移完成")
except Exception as e:
    print(f"[启动] 数据库初始化警告: {e}")

# ========== 应用退出时关闭连接池 ==========
atexit.register(db_service.close_all)

# ========== 配置区 ==========
app.json.ensure_ascii = False

app.config.update(
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    JSON_AS_ASCII=False,
)

# ========== 全局状态 ==========
# 对话状态机实例（已在顶部创建 chat_state = ChatState()）
# 注：原 chat_history / pending_operation 已迁移至 chat_state 内部管理

# ========== 二次确认开关（模块级，全局可见）==========
NEED_CONFIRM_DELETE = True
NEED_CONFIRM_ASSIGN = True
NEED_CONFIRM_SCHEDULE = True

# ========== 路由区 ==========

@app.route("/")
def index():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "message": "数字人智能助手后端运行中",
        "version": "1.0.0"
    })


@app.route("/chat", methods=["POST"])
def chat():
    """对话接口（状态机驱动，支持多轮 + 二次确认 + 监控查询）"""
    global NEED_CONFIRM_DELETE, NEED_CONFIRM_ASSIGN, NEED_CONFIRM_SCHEDULE

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求体不能为空"}), 400

    text = data.get("text", "")

    # 读取配置：二次确认开关
    _confirm_delete = db_service.get_config_value("confirm_delete", "1")
    _confirm_assign = db_service.get_config_value("confirm_assign", "1")
    _confirm_schedule = db_service.get_config_value("confirm_schedule", "1")
    NEED_CONFIRM_DELETE = _confirm_delete == "1"
    NEED_CONFIRM_ASSIGN = _confirm_assign == "1"
    NEED_CONFIRM_SCHEDULE = _confirm_schedule == "1"
    audio_data = data.get("audio_data", "")

    if not text and not audio_data:
        return jsonify({"error": "请提供 text 或 audio_data"}), 400

    # 1. ASR 语音识别
    if audio_data and not text:
        try:
            text = asr_service.recognize_from_base64(audio_data)
        except Exception as e:
            print(f"[ASR] 识别失败: {e}")
            return jsonify({"error": "语音识别失败"}), 500

    if not text:
        return jsonify({"error": "无法获取文本输入"}), 400

    print(f"[对话] 用户: {text} | 状态: {chat_state.state}")

    # 2. 修复卡死状态：如果状态机卡在 EXECUTING（前序执行未正常回到 IDLE），强制复位
    if chat_state.state == "EXECUTING":
        print(f"[对话] ⚠️ 状态卡死在 EXECUTING，自动复位到 IDLE")
        chat_state.context.clear_pending()
        chat_state.transition("IDLE")

    # 3. 状态驱动处理
    if chat_state.is_awaiting_confirmation:
        return _handle_confirmation_fsm(text)

    # 4. 保存用户输入 → 进入处理状态
    chat_state.context.add_turn("user", text)
    chat_state.start_processing()

    # 5. 规则预检：匹配已知的排班查询/导航/操作关键词，直接走意图执行（绕过 LLM 避免误识别）
    import re as _re
    rule_intent = None
    # 排班查询：今日值班/当前在线/本月排班/查询XX日排班
    if _re.search(r'(今日|今天).*值班|查询.*值班|值班.*情况', text):
        rule_intent = {"intent": "schedule_query", "api": "schedule_today", "params": {}}
    elif _re.search(r'当前在线|在线人数|谁在线', text):
        rule_intent = {"intent": "schedule_query", "api": "schedule_online", "params": {}}
    elif _re.search(r'本月排班|排班统计', text):
        rule_intent = {"intent": "schedule_query", "api": "schedule_month_stats", "params": {}}
    else:
        # 排班操作：让XX排某日某班
        sd = _re.search(r'让\s*(\S+?)\s*排\s*(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:的)?\s*(早班|下午班|晚班|休息)', text)
        if sd:
            import datetime as _dt
            year = sd.group(2) or str(_dt.datetime.now().year)
            rule_intent = {"intent": "operate", "api": "schedule_assign",
                           "params": {"staff_name": sd.group(1), "shift_date": f"{year}-{sd.group(3).zfill(2)}-{sd.group(4).zfill(2)}", "shift_type": sd.group(5)}}
        else:
            # 排班详情：XX月XX日（XX班）排班
            dd = _re.search(r'(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:的)?\s*(早班|下午班|晚班)?\s*(?:排班|值班|情况)', text)
            if dd:
                year = dd.group(1) or str(_dt.datetime.now().year)
                shift = dd.group(4) or None
                params = {"date": f"{year}-{dd.group(2).zfill(2)}-{dd.group(3).zfill(2)}"}
                if shift: params["shift_type"] = shift
                rule_intent = {"intent": "schedule_query", "api": "schedule_detail", "params": params}

    if rule_intent:
        print(f"[意图] 规则预检命中: intent={rule_intent.get('intent')} api={rule_intent.get('api','')}")
        return execute_action_fsm(rule_intent, text)

    # 6. LLM 理解意图
    try:
        ctx_str = chat_state.context.to_prompt_context()
        intent_data = ollama_service.understand_intent(text, context_str=ctx_str)
        print(f"[意图] intent={intent_data.get('intent')} api={intent_data.get('api','')} params={intent_data.get('params',{})}")

        # 7. 执行意图
        return execute_action_fsm(intent_data, text)
    except Exception as e:
        print(f"[对话] ❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        chat_state.context.clear_pending()
        chat_state.state = "IDLE"
        return jsonify({"reply_text": "抱歉，处理请求时出错了，请重试"}), 500


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    """
    语音转写接口：接收 WebM/WAV 音频文件，自动转换为 WAV 后识别
    前端用 FormData 上传 file 字段
    """
    if "file" not in request.files:
        return jsonify({"error": "请上传音频文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名为空"}), 400

    try:
        import tempfile
        import os
        import subprocess

        # 保存原始上传文件
        raw_ext = os.path.splitext(file.filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(suffix=raw_ext, delete=False) as tmp:
            file.save(tmp.name)
            raw_path = tmp.name

        # 转换为 16kHz mono WAV（FunASR 需要的格式）
        wav_path = raw_path + "_16k.wav"
        print(f"[转写] 原始文件: {file.filename}, 大小: {os.path.getsize(raw_path)} bytes")

        # 用 ffmpeg 转码
        result = subprocess.run([
            r"C:\ffmpeg\bin\ffmpeg.exe", "-y",
            "-i", raw_path,
            "-ar", "16000",      # 16kHz 采样率
            "-ac", "1",           # 单声道
            "-sample_fmt", "s16", # 16-bit PCM
            wav_path
        ], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            print(f"[转写] ffmpeg 转码失败: {result.stderr}")
            # 尝试直接识别原始文件（可能是 WAV）
            text = asr_service.recognize_from_file(raw_path)
        else:
            print(f"[转写] 转码完成, WAV 大小: {os.path.getsize(wav_path)} bytes")
            text = asr_service.recognize_from_file(wav_path)

        # 清理临时文件
        os.unlink(raw_path)
        if os.path.exists(wav_path):
            os.unlink(wav_path)

        print(f"[转写] 结果: {text}")
        return jsonify({"text": text})

    except Exception as e:
        print(f"[转写] 失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ========== TTS 语音合成接口 ==========

@app.route("/api/tts", methods=["POST"])
def tts_synthesize():
    """
    TTS 语音合成接口
    接收：{"text": "你好", "rate": -2, "voice": "zh-CN-XiaoxiaoNeural"}
    返回：WAV 音频流（audio/wav）
    """
    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"error": "请提供 text 参数"}), 400

    text = data["text"].strip()
    if not text:
        return jsonify({"error": "text 不能为空"}), 400

    rate = data.get("rate", -2)
    voice = data.get("voice", "sherpa-0")

    try:
        from flask import Response
        wav_bytes = tts_service.synthesize_to_wav(text, rate=rate, voice_name=voice)
        return Response(wav_bytes, mimetype="audio/wav",
                        headers={"Content-Disposition": "inline; filename=tts.wav"})
    except Exception as e:
        print(f"[TTS] 合成失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tts/voices", methods=["GET"])
def tts_list_voices():
    """获取可用 TTS 语音列表"""
    return jsonify(tts_service.list_available_voices())


# ========== 对话管理接口 ==========

@app.route("/api/chat/reset", methods=["POST"])
def reset_chat():
    """重置对话状态"""
    global chat_state
    chat_state = ChatState()
    return jsonify({"success": True, "message": "对话已重置"})


@app.route("/api/chat/debug", methods=["GET"])
def debug_chat_state():
    """调试：查看当前状态机信息"""
    return jsonify(chat_state.dump())


@app.route("/api/chat/debug_rule", methods=["POST"])
def debug_rule_match():
    """调试：测试规则匹配"""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "请提供 text"}), 400
    result = ollama_service._rule_based_navigate(text)
    return jsonify({"input": text, "rule_result": result})


# ========== 意图执行引擎（FSM 版） ==========

def _strip_emoji(text: str) -> str:
    """去除文本中的 emoji 和特殊符号（如 ⚠️），避免 TTS 读出警告标志"""
    import re
    # 移除常见 emoji 字符（Unicode 范围 1F300-1F9FF, 2600-26FF, 2700-27BF 等）
    emoji_pattern = re.compile(
        "[\U0001F300-\U0001F9FF"  # Misc symbols, emoticons, etc
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"   # Misc symbols (⚠☀★ etc)
        "\U00002700-\U000027BF"   # Dingbats
        "\uFE00-\uFE0F"           # Variation selectors
        "\U000020D0-\U000020FF"   # Combining marks
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub('', text).strip()


def execute_action_fsm(intent_data: dict, user_text: str):
    intent = intent_data.get("intent", "unknown")
    reply_text = ""
    action = None
    target = None
    need_confirmation = False

    if intent == "error":
        reply_text = f"抱歉，{intent_data.get('message', '系统繁忙，请重试')}"

    elif intent == "greeting":
        reply_text = "你好！我是轻言OPS 智能助手，可以帮你查询工单、监控数据，或者跳转页面。"

    elif intent == "navigate":
        target = intent_data.get("params", {}).get("target", "/")
        action = "navigate"
        # 改进：把目标路径映射成友好中文页面名，播报更自然
        page_name_map = {
            "/": "首页",
            "/monitor": "监控大盘",
            "/tickets": "工单列表",
            "/tickets/stats": "统计看板",
            "/tickets/config": "工单参数配置",
            "/staff": "人员管理",
            "/staff/schedule": "排班管理",
            "/staff/roles": "角色配置",
        }
        page_name = page_name_map.get(target, target)
        reply_text = f"好的，正在为你打开{page_name}"

    elif intent == "summary":
        # 趋势总结：直接基于看板趋势数据，不调 LLM，简洁可靠
        import datetime as _dt
        params = intent_data.get("params", {})
        try:
            today = _dt.date.today()
            start = params.get("start_date") or (today - _dt.timedelta(days=30)).isoformat()
            end   = params.get("end_date")   or today.isoformat()
            # 时间格式校验
            try:
                _dt.datetime.strptime(start, "%Y-%m-%d")
                _dt.datetime.strptime(end,   "%Y-%m-%d")
            except ValueError:
                start = (today - _dt.timedelta(days=30)).isoformat()
                end   = today.isoformat()
            try:
                report = db_service.get_tickets_report(start, end)
                reply_text = ollama_service.summarize_report(user_text, report)
            except Exception as e:
                print(f"[summary] DB 失败: {e}")
                reply_text = f"抱歉，生成趋势报告失败（{type(e).__name__}），请稍后重试。"
        except Exception as e:
            print(f"[summary] 兜底异常: {e}")
            reply_text = "抱歉，生成趋势报告时出现未知错误，请稍后重试。"

    elif intent == "query":
        api = intent_data.get("api", "")
        params = intent_data.get("params", {})
        if api == "tickets_stat":
            filter_status = params.get("status", "")
            filter_priority = params.get("priority", "")
            start_date = params.get("start_date") or None
            end_date = params.get("end_date") or None
            if filter_status or filter_priority:
                # 用 search_tickets_dynamic 支持 status+priority+date 任意组合
                sp = {}
                if filter_status: sp["status"] = filter_status
                if filter_priority: sp["priority"] = filter_priority
                if start_date: sp["start_date"] = start_date
                if end_date: sp["end_date"] = end_date
                result = db_service.search_tickets_dynamic(sp)
                parts = []
                if filter_status: parts.append(filter_status)
                if filter_priority: parts.append(f"{filter_priority}优先级")
                api_result = {"total": result["total"], "status": "·".join(parts)}
            else:
                api_result = db_service.get_tickets_stat(
                    start_date=start_date, end_date=end_date
                )
            reply_text = ollama_service.summarize_data(user_text, api_result)
            # 存储查询上下文，便于后续"其中有多少XX"等连续问答
            chat_state.context.last_entity = {
                "type": "ticket_stat",
                "filter_status": filter_status,
                "filter_priority": filter_priority,
                "start_date": start_date,
                "end_date": end_date,
                "total": api_result.get("total", 0),
                "status_label": api_result.get("status", ""),
            }
        elif api == "tickets_detail":
            tid = _normalize_ticket_id(params.get("id"))
            ticket = db_service.get_ticket_by_id(tid)
            if ticket:
                reply_text = f"工单{tid}：{ticket['title']}，状态「{ticket['status']}」，优先级{ticket['priority']}，负责人{ticket['assignee']}。"
                chat_state.context.last_entity = {"type": "ticket", "id": tid, "title": ticket["title"]}
            else:
                reply_text = f"未找到工单 {tid}。"
        else:
            # 兜底：LLM 可能自己发明了 api 名但 params 里带了 id
            tid = _normalize_ticket_id(params.get("id"))
            if tid:
                ticket = db_service.get_ticket_by_id(tid)
                if ticket:
                    reply_text = f"工单{tid}：{ticket['title']}，状态「{ticket['status']}」，优先级{ticket['priority']}，负责人{ticket['assignee']}。"
                    chat_state.context.last_entity = {"type": "ticket", "id": tid, "title": ticket["title"]}
                else:
                    reply_text = f"未找到工单 {tid}。"
            else:
                reply_text = "抱歉，我还不能理解这个查询"

    elif intent == "search":
        # 多条件动态搜索：参数由 LLM 按 6 类参数严格提取
        # （ticket_id / assignee / status / priority / keyword / start_date / end_date）
        try:
            search_params = intent_data.get("params", {}) or {}
            # 1) 真正调后端动态 SQL
            search_result = db_service.search_tickets_dynamic(search_params)

            # 2) 区分"数量查询"和"列表查询"
            #    当用户问"XX有多少工单"时，直接返回数字，不走 LLM 润色避免幻觉
            import re as _re
            is_count_query = bool(
                _re.search(r'多少|几个|几条|数量|统计', user_text)
                and search_params.get("assignee")
            )
            if is_count_query:
                total = search_result.get("total", 0)
                assignee = search_params.get("assignee", "")
                priority = search_params.get("priority", "")
                status = search_params.get("status", "")
                if total > 0:
                    if priority:
                        reply_text = f"{assignee}共有{total}个{priority}优先级工单。"
                    elif status:
                        reply_text = f"{assignee}共有{total}个{status}工单。"
                    else:
                        reply_text = f"{assignee}共有{total}个工单。"
                else:
                    cond = f"{priority}优先级" if priority else (status or "")
                    cond_str = f"{cond}的" if cond else ""
                    reply_text = f"{assignee}名下没有{cond_str}工单。"
            else:
                # 3) 语音播报（润色）；0 命中时走硬编码分支
                reply_text = ollama_service.polish_search_result(user_text, search_result)

            # 4) 联动信号：让前端可同步刷新筛选器
            chat_state.context.last_entity = {
                "type": "ticket_search",
                "applied_filters": search_result.get("applied_filters", {}),
                "total": search_result.get("total", 0),
            }
        except Exception as e:
            print(f"[search] 处理失败: {e}")
            reply_text = "抱歉，多条件搜索执行失败，请稍后重试。"

    elif intent == "query_monitor":
        api = intent_data.get("api", "monitor_latest")
        params = intent_data.get("params", {})
        target_field = params.get("target", "all")
        period = params.get("period", "latest")

        if api == "monitor_history":
            mins = {"5min": 5, "30min": 30, "1h": 60}.get(period, 30)
            history = db_service.get_historical_metrics(mins)
            if history and len(history) > 0:
                latest = history[-1]
                reply_text = ollama_service.summarize_data(
                    f"最近{period}的{target_field}监控数据",
                    {"period": period, "samples": len(history), "latest": latest}
                )
            else:
                reply_text = "暂无历史监控数据"
        else:
            metrics = db_service.get_latest_metrics()
            if metrics:
                if target_field == "cpu":
                    cpu_val = psutil.cpu_percent(interval=0.5)
                    reply_text = f"当前 CPU 使用率 {cpu_val:.1f}%。"
                elif target_field == "memory":
                    mem_val = psutil.virtual_memory().percent
                    reply_text = f"当前内存使用率 {mem_val:.1f}%。"
                elif target_field == "disk":
                    reply_text = f"磁盘读取 {metrics.get('disk_read_mbps', 0):.1f} Mbps，写入 {metrics.get('disk_write_mbps', 0):.1f} Mbps。"
                elif target_field == "network":
                    reply_text = f"网络上行 {metrics.get('network_in_mbps', 0):.1f} Mbps，下行 {metrics.get('network_out_mbps', 0):.1f} Mbps。"
                else:
                    reply_text = ollama_service.summarize_data(user_text, metrics)
                chat_state.context.last_entity = {"type": "monitor", "field": target_field}
            else:
                reply_text = "暂无监控数据，请稍后重试"

    elif intent == "staff_query":
        api = intent_data.get("api", "staff_count")
        if api == "staff_count":
            # 查询人员统计数据
            staff_list = db_service.get_staff_list()
            total = len(staff_list)
            active = sum(1 for s in staff_list if s.get("status") == "启用")
            roles = db_service.get_staff_roles()
            role_names = ", ".join(r["role_name"] for r in roles[:5])
            reply_text = f"当前共有 {total} 名运维人员，其中在职 {active} 人。岗位角色包括：{role_names}等。"

    elif intent == "schedule_query":
        api = intent_data.get("api", "")
        params = intent_data.get("params", {})
        if api == "schedule_today":
            data = db_service.get_schedule_today()
            shifts = data.get("grouped", {})
            total = data.get("total_on_duty", 0)
            if total == 0:
                reply_text = "今日暂无排班记录。"
            else:
                parts = [f"今日共有 {total} 人值班"]
                for st in ("早班", "下午班", "晚班"):
                    names = shifts.get(st, [])
                    if names:
                        parts.append(f"{st}：{'、'.join(names)}")
                reply_text = "，".join(parts) + "。"
        elif api == "schedule_online":
            data = db_service.get_schedule_online()
            cnt = data["online_count"]
            reply_text = f"当前共有 {cnt} 名运维人员在线。"
        elif api == "schedule_month_stats":
            data = db_service.get_schedule_month_stats()
            kpi = data.get("kpi", {})
            month_total = kpi.get("month_total_shifts", 0)
            today_on_duty = kpi.get("today_on_duty", 0)
            load_data = data.get("load_data", [])
            parts = [f"本月累计排班 {month_total} 次，今日值班 {today_on_duty} 人"]
            if load_data:
                top = load_data[:3]
                top_parts = [f"{ld['staff_name']}({ld['duty_days']}天)" for ld in top]
                parts.append(f"排班最多的是{'、'.join(top_parts)}")
            reply_text = "，".join(parts) + "。"
        elif api == "schedule_detail":
            date = params.get("date", "")
            shift_type = params.get("shift_type", None)
            if not date:
                reply_text = "请说明要查询哪一天的排班情况，例如：7月23日的早班排班情况。"
            else:
                data = db_service.get_schedule_by_date(date, shift_type)
                grouped = data.get("grouped", {})
                total = data.get("total_on_duty", 0)
                if total == 0:
                    reply_text = f"{date} 暂无排班记录。"
                else:
                    parts = [f"{date} 共有 {total} 人值班"]
                    for st in ("早班", "下午班", "晚班"):
                        names = grouped.get(st, [])
                        if names:
                            parts.append(f"{st}：{'、'.join(names)}")
                    reply_text = "，".join(parts) + "。"
        else:
            reply_text = "抱歉，我还不能理解这个排班查询。"

    elif intent == "delete":
        params = intent_data.get("params", {})
        ticket_id = _normalize_ticket_id(params.get("id"))
        # 如果 LLM 把"六"识别为 6，但 params["id"] 可能是字符串"六"
        # 尝试从上下文 last_entity 获取
        if not ticket_id:
            last = chat_state.context.last_entity or {}
            if last.get("type") == "ticket" and last.get("id"):
                ticket_id = last["id"]
        if not ticket_id or not isinstance(ticket_id, (int, str)):
            reply_text = "请说明要删除哪个工单，例如：删除工单5。"
        else:
            ticket = db_service.get_ticket_by_id(ticket_id)
            if not ticket:
                reply_text = f"未找到工单 {ticket_id}，无法删除。"
            else:
                if NEED_CONFIRM_DELETE:
                    chat_state.await_confirmation(
                        {"api": "tickets_delete", "params": {"id": ticket_id}, "ticket_title": ticket["title"]},
                        {"type": "ticket", "id": ticket_id, "title": ticket["title"]}
                    )
                    reply_text = (
                        f"⚠️ 您确定要删除工单「{ticket['title']}」吗？"
                        f"此操作不可恢复，请说「确认」或「取消」。"
                    )
                    need_confirmation = True
                else:
                    # 配置关闭了删除确认，直接执行
                    result = db_service.delete_ticket(ticket_id)
                    if result:
                        reply_text = f"已删除工单「{ticket['title']}」。"
                    else:
                        reply_text = f"删除工单「{ticket['title']}」失败。"

    elif intent == "operate":
        api = intent_data.get("api", "")
        params = intent_data.get("params", {})
        if api == "tickets_update":
            ticket_id = _normalize_ticket_id(params.get("id"))
            new_status = params.get("status")
            ticket = db_service.get_ticket_by_id(ticket_id)
            if not ticket:
                reply_text = f"未找到工单 {ticket_id}"
            else:
                chat_state.await_confirmation(
                    {"api": "tickets_update", "params": {"id": ticket_id, "status": new_status},
                     "ticket_title": ticket["title"]},
                    {"type": "ticket", "id": ticket_id, "title": ticket["title"]}
                )
                reply_text = f"您确定要将工单「{ticket['title']}」修改为「{new_status}」吗？请说「确认」或「取消」。"
                need_confirmation = True
        elif api == "tickets_assign":
            ticket_id = _normalize_ticket_id(params.get("id"))
            new_assignee = params.get("assignee", "")
            ticket = db_service.get_ticket_by_id(ticket_id)
            if not ticket:
                reply_text = f"未找到工单 {ticket_id}，无法指派。"
            elif not new_assignee:
                reply_text = "请说明要指派给谁，例如：把工单5指派给李四。"
            else:
                if NEED_CONFIRM_ASSIGN:
                    chat_state.await_confirmation(
                        {"api": "tickets_assign", "params": {"id": ticket_id, "assignee": new_assignee},
                         "ticket_title": ticket["title"]},
                        {"type": "ticket", "id": ticket_id, "title": ticket["title"]}
                    )
                    reply_text = f"您确定要将工单「{ticket['title']}」指派给{new_assignee}吗？请说「确认」或「取消」。"
                    need_confirmation = True
                else:
                    result = db_service.update_ticket(ticket_id, assignee=new_assignee)
                    if result:
                        reply_text = f"已将工单「{ticket['title']}」指派给{new_assignee}。"
                    else:
                        reply_text = f"指派工单「{ticket['title']}」给{new_assignee}失败。"
        elif api == "schedule_assign":
            staff_name = intent_data.get("params", {}).get("staff_name", "")
            shift_date = params.get("shift_date", "")
            shift_type = params.get("shift_type", "")
            # 正则修正：从用户原文中提取真实姓名，防止 LLM 姓名幻觉（如"赵敏"→"赵六"）
            import re as _re
            name_match = _re.search(r'让\s*(\S+?)\s*排', user_text)
            if name_match:
                extracted_name = name_match.group(1)
                if extracted_name != staff_name and len(extracted_name) >= 2:
                    print(f"[schedule_assign] 姓名修正: LLM={staff_name} → 原文={extracted_name}")
                    staff_name = extracted_name
            if not staff_name or not shift_date or not shift_type:
                reply_text = "请说明要排班的人员、日期和班次，例如：让王强排7月23日的早班。"
            elif shift_type not in ("早班", "下午班", "晚班", "休息"):
                reply_text = f"班次类型「{shift_type}」无效，请使用：早班、下午班、晚班、休息。"
            else:
                if NEED_CONFIRM_SCHEDULE:
                    chat_state.await_confirmation(
                        {"api": "schedule_assign", "params": {"staff_name": staff_name, "shift_date": shift_date, "shift_type": shift_type}},
                        {"type": "schedule", "staff_name": staff_name, "shift_date": shift_date, "shift_type": shift_type}
                    )
                    reply_text = f"您确定要让{staff_name}在{shift_date}排{shift_type}吗？请说「确认」或「取消」。"
                    need_confirmation = True
                else:
                    assign_result = db_service.assign_schedule(staff_name, shift_date, shift_type)
                    if assign_result["success"]:
                        reply_text = f"已为{staff_name}在{shift_date}安排了{shift_type}。"
                    else:
                        reply_text = f"排班操作失败：{assign_result.get('error', '未知错误')}"
        else:
            # 兜底：LLM 可能自己造了 api 名但 params 里带了 id+status
            ticket_id = _normalize_ticket_id(params.get("id"))
            new_status = params.get("status")
            if ticket_id and new_status:
                ticket = db_service.get_ticket_by_id(ticket_id)
                if ticket:
                    chat_state.await_confirmation(
                        {"api": "tickets_update", "params": {"id": ticket_id, "status": new_status},
                         "ticket_title": ticket["title"]},
                        {"type": "ticket", "id": ticket_id, "title": ticket["title"]}
                    )
                    reply_text = f"您确定要将工单「{ticket['title']}」修改为「{new_status}」吗？请说「确认」或「取消」。"
                    need_confirmation = True
                else:
                    reply_text = f"未找到工单 {ticket_id}。"
            else:
                reply_text = "抱歉，我还不能执行这个操作"

    else:
        reply_text = "请提问系统相关问题，例如：查工单、排班管理、CPU 使用率、打开监控等。"

    # 保存助手回复（去除非语言符号）
    reply_text = _strip_emoji(reply_text)
    chat_state.context.add_turn("assistant", reply_text)

    if not need_confirmation:
        chat_state.reply_and_idle()

    # 拿到最近一次的工单搜索上下文（如果上一个意图是 search）
    last_entity = getattr(chat_state.context, "last_entity", None) or {}
    sync_filters = last_entity.get("applied_filters") if last_entity.get("type") == "ticket_search" else None

    # TTS 组合反馈（"组合拳"播报：先说"收到！正在执行..."，再播真实结果）
    # 适用于"写操作类"意图：delete / assign / operate（修改工单状态）
    # query/navigate/search/summary/query_monitor/greeting 不需要
    pre_tts = None
    pre_tts_intents = {"delete", "operate"}
    if intent in pre_tts_intents and not need_confirmation and reply_text:
        # 友好提示 + 真实操作结果，组合播报
        verb_map = {"delete": "删除", "assign": "指派", "operate": "修改"}
        verb = verb_map.get(intent, "执行")
        pre_tts = f"收到！正在为你{verb}…"

    return jsonify({
        "reply_text": reply_text,
        "action": action,
        "target": target,
        "need_confirmation": need_confirmation,
        "pending_timeout_sec": chat_state.context.PENDING_TIMEOUT_SEC if need_confirmation else 0,
        "sync_filters": sync_filters,
        "pre_tts": pre_tts,
    })


def _handle_confirmation_fsm(text: str):
    """处理二次确认（FSM 版）"""
    # 入口先检查是否已超时（30 秒未确认 → 自动取消 + 释放资源）
    if chat_state.context.is_pending_expired():
        op = chat_state.context.pending_operation or {}
        chat_state.cancel_and_idle()  # 顺手把 transition AWAITING -> IDLE 也做完
        timeout_sec = chat_state.context.PENDING_TIMEOUT_SEC
        # 按操作类型给出不同的超时提示
        if op.get("api") == "schedule_assign":
            p = op.get("params", {})
            desc = f"让{p.get('staff_name','')}在{p.get('shift_date','')}排{p.get('shift_type','')}"
        else:
            desc = f"工单「{op.get('ticket_title', '')}」"
        reply = (
            f"由于超过 {timeout_sec} 秒未收到您对{desc}"
            f"的二次确认，本次操作已自动取消。如仍需执行，请重新发起指令。"
        )
        reply = _strip_emoji(reply)
        chat_state.context.add_turn("assistant", reply)
        return jsonify({"reply_text": reply, "need_confirmation": False, "pending_timeout_sec": 0})

    result = chat_state.handle_confirmation_input(text)

    if result is False:
        op = chat_state.context.pending_operation or {}
        if op.get("api") == "schedule_assign":
            p = op.get("params", {})
            reply = f"已取消{p.get('staff_name','')}在{p.get('shift_date','')}的{p.get('shift_type','')}排班操作。"
        else:
            reply = f"已取消对工单「{op.get('ticket_title', '')}」的修改操作。"
        chat_state.cancel_and_idle()
        reply = _strip_emoji(reply)
        chat_state.context.add_turn("assistant", reply)
        return jsonify({"reply_text": reply, "need_confirmation": False, "pending_timeout_sec": 0})

    if result is True:
        try:
            op = chat_state.confirm_and_execute()
            reply = _do_execute(op)
            refresh_schedule = (op.get("api") == "schedule_assign")
        except Exception as e:
            print(f"[对话] 执行确认操作失败: {e}")
            reply = "抱歉，执行操作时出错了，请重试。"
            refresh_schedule = False
        finally:
            chat_state.context.clear_pending()
            chat_state.state = "IDLE"
            reply = _strip_emoji(reply)
            chat_state.context.add_turn("assistant", reply)
        return jsonify({"reply_text": reply, "need_confirmation": False, "pending_timeout_sec": 0, "refresh_schedule": refresh_schedule})

    # 无法识别
    op = chat_state.context.pending_operation or {}
    if op.get("api") == "schedule_assign":
        p = op.get("params", {})
        desc = f"是否让{p.get('staff_name','')}在{p.get('shift_date','')}排{p.get('shift_type','')}"
    else:
        desc = f"是否修改工单「{op.get('ticket_title', '')}」"
    reply = f"请明确回答「确认」或「取消」：{desc}？"
    return jsonify({
        "reply_text": reply,
        "need_confirmation": True,
        "pending_timeout_sec": chat_state.context.PENDING_TIMEOUT_SEC,
    })


def _do_execute(op: dict) -> str:
    """实际执行数据库写操作，含状态机校验"""
    try:
        if op.get("api") == "tickets_update":
            tid = op["params"]["id"]
            new_st = op["params"]["status"]
            ticket = db_service.get_ticket_by_id(tid)
            if ticket:
                ok = db_service.update_ticket_status(tid, new_st)
                if ok:
                    return f"已将工单「{ticket['title']}」状态更新为「{new_st}」。"
                return f"工单 {tid} 状态更新失败。"
            return f"工单 {tid} 不存在。"

        if op.get("api") == "tickets_delete":
            # 二次确认后真正执行删除，按结果返回精细提示
            tid = op["params"]["id"]
            result = db_service.delete_ticket(tid)
            if result.get("ok"):
                return f"已删除工单「{result['title']}」（ID={tid}）。"
            reason = result.get("reason", "unknown")
            if reason == "not_found":
                return f"工单 {tid} 已被他人删除或不存在。"
            if reason == "db_error":
                return f"删除工单 {tid} 失败：数据库错误（{result.get('error','')}）。"
            if reason == "invalid_id":
                return f"工单 ID {tid} 非法，请重新发起指令。"
            if "只能删除未完成的工单" in reason:
                return f"工单「{result.get('id', tid)}」当前状态不允许删除，只有未完成的工单才能删除。"
            return f"删除工单 {tid} 失败：未知原因。"

        if op.get("api") == "tickets_assign":
            tid = op["params"]["id"]
            new_assignee = op["params"]["assignee"]
            result = db_service.assign_ticket(tid, new_assignee)
            if result.get("ok"):
                return f"已把工单「{result['ticket']['title']}」指派给{new_assignee}。"
            return result.get("reason", "指派失败")

        if op.get("api") == "schedule_assign":
            p = op["params"]
            result = db_service.assign_schedule(p["staff_name"], p["shift_date"], p["shift_type"])
            if result.get("ok"):
                return f"已为{p['staff_name']}在{p['shift_date']}安排{p['shift_type']}。"
            return result.get("reason", "排班操作失败")

        return "操作已完成。"

    except ValueError as e:
        # 状态机校验失败 → 返回友好提示
        return str(e)


# ========== 数据库接口 ==========
@app.route("/api/tickets", methods=["GET"])
def tickets_list():
    """获取全部工单列表（从数据库读取）"""
    try:
        tickets = db_service.get_tickets()
        return jsonify(tickets)
    except Exception as e:
        print(f"[DB] 查询工单列表失败: {e}")
        return jsonify({"error": "数据库查询失败"}), 500

@app.route("/api/tickets/stat", methods=["GET"])
def tickets_stat():
    """工单状态统计（从数据库读取）"""
    try:
        stat = db_service.get_tickets_stat()
        return jsonify(stat)
    except Exception as e:
        print(f"[DB] 查询工单统计失败: {e}")
        return jsonify({"error": "数据库查询失败"}), 500


@app.route("/api/tickets/page", methods=["GET"])
def tickets_page():
    """
    分页查询工单列表（支持多条件筛选 + 关键词 + 日期）
    ?page=1&limit=10&keyword=xxx&status=未完成&priority=高&assignee=张三&date=2026-07-05
    ?page=1&limit=10&date_start=2026-07-01&date_end=2026-07-31
    """
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 10, type=int)
    keyword = request.args.get("keyword", "", type=str).strip() or None
    status = request.args.get("status", "", type=str).strip() or None
    priority = request.args.get("priority", "", type=str).strip() or None
    assignee = request.args.get("assignee", "", type=str).strip() or None
    # 日期参数：前端以 date（单日）或 date_start+date_end（时间段）发送
    date = request.args.get("date", "", type=str).strip() or None
    date_start = request.args.get("date_start", "", type=str).strip() or None
    date_end = request.args.get("date_end", "", type=str).strip() or None
    # 统一为 start/end：单日模式时 date 同时充当起止
    if date:
        date_start = date_end = date
    try:
        result = db_service.get_tickets_page(
            page=page, limit=limit, keyword=keyword,
            status=status, priority=priority, assignee=assignee,
            date_start=date_start, date_end=date_end,
        )
        return jsonify(result)
    except Exception as e:
        print(f"[DB] 分页查询失败: {e}")
        return jsonify({"data": [], "total": 0, "page": 1, "limit": 10, "total_pages": 0, "error": str(e)}), 500


@app.route("/api/stats/dashboard", methods=["GET"])
def stats_dashboard():
    """工单统计看板聚合接口（支持 ?days=7/14/30 参数）"""
    try:
        days = request.args.get("days", 7, type=int)
        # 限制范围 1~90 天
        days = max(1, min(90, days))
        result = db_service.get_dashboard_stats(days=days)
        return jsonify(result)
    except Exception as e:
        print(f"[API] 获取统计看板数据失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "获取数据失败"}), 500


@app.route("/api/config/params", methods=["GET", "PUT"])
def config_params():
    """系统参数配置：GET 读取 / PUT 写入"""
    if request.method == "GET":
        try:
            cfg = db_service.get_config()
            return jsonify(cfg)
        except Exception as e:
            print(f"[API] 读取配置失败: {e}")
            return jsonify({"error": "读取配置失败"}), 500
    elif request.method == "PUT":
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "请求体不能为空"}), 400
        try:
            result = db_service.save_config(data)
            return jsonify({"success": True, "updated": result["updated"]})
        except Exception as e:
            print(f"[API] 保存配置失败: {e}")
            return jsonify({"error": "保存配置失败"}), 500


# ========== 人员管理接口 ==========

@app.route("/api/staff/list", methods=["GET"])
def staff_list():
    """获取人员列表（支持 keyword 搜索）"""
    keyword = request.args.get("keyword", "", type=str).strip() or None
    try:
        result = db_service.get_staff_list(keyword)
        return jsonify(result)
    except Exception as e:
        print(f"[API] 获取人员列表失败: {e}")
        return jsonify({"error": "获取数据失败"}), 500


@app.route("/api/staff", methods=["POST"])
def staff_create():
    """新增人员"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "reason": "请求体不能为空"}), 400
    try:
        result = db_service.create_staff(data)
        return jsonify(result)
    except Exception as e:
        print(f"[API] 新增人员失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/<int:staff_id>", methods=["PUT"])
def staff_update(staff_id):
    """编辑人员信息"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "reason": "请求体不能为空"}), 400
    try:
        result = db_service.update_staff(staff_id, data)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        print(f"[API] 更新人员失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/<int:staff_id>/reset-password", methods=["POST"])
def staff_reset_password(staff_id):
    """重置人员密码"""
    try:
        body = request.get_json(silent=True) or {}
        new_pwd = body.get("password") or "123456"
        result = db_service.reset_staff_password(staff_id, new_pwd)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        print(f"[API] 重置密码失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/<int:staff_id>/detail", methods=["GET"])
def staff_detail(staff_id):
    """获取人员详情（含最近5条待处理工单）"""
    try:
        result = db_service.get_staff_detail(staff_id)
        if not result:
            return jsonify({"error": "人员不存在"}), 404
        return jsonify(result)
    except Exception as e:
        print(f"[API] 获取人员详情失败: {e}")
        return jsonify({"error": str(e)}), 500


# ========== 排班管理接口 ==========

@app.route("/api/staff/schedule", methods=["GET", "POST"])
def staff_schedule():
    """排班管理：GET 获取 / POST 生成"""
    if request.method == "GET":
        try:
            year = request.args.get("year", type=int)
            month = request.args.get("month", type=int)
            result = db_service.get_schedule(year=year, month=month)
            return jsonify(result)
        except Exception as e:
            print(f"[API] 获取排班数据失败: {e}")
            return jsonify({"error": str(e)}), 500
    elif request.method == "POST":
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"ok": False, "reason": "请求体不能为空"}), 400
        try:
            result = db_service.create_schedule(data)
            if not result.get("ok"):
                return jsonify(result), 400
            return jsonify(result)
        except Exception as e:
            print(f"[API] 保存排班失败: {e}")
            return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/schedule/delete", methods=["POST"])
def staff_schedule_delete():
    """删除单条排班"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "reason": "请求体不能为空"}), 400
    try:
        result = db_service.delete_schedule(data)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        print(f"[API] 删除排班失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/schedule/batch", methods=["POST"])
def staff_schedule_batch():
    """批量排班：按周几循环生成"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "reason": "请求体不能为空"}), 400
    try:
        result = db_service.batch_create_schedule(data)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        print(f"[API] 批量排班失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


# ========== 角色配置接口 ==========

@app.route("/api/staff/roles", methods=["GET", "POST", "PUT", "DELETE"])
def staff_roles():
    """角色管理：GET 列表 / POST 新增 / PUT 编辑 / DELETE 删除"""
    if request.method == "GET":
        try:
            result = db_service.get_staff_roles()
            return jsonify(result)
        except Exception as e:
            print(f"[API] 获取角色列表失败: {e}")
            return jsonify([]), 500
    elif request.method == "POST":
        data = request.get_json(silent=True)
        if not data or not data.get("role_name"):
            return jsonify({"ok": False, "reason": "角色名不能为空"}), 400
        try:
            result = db_service.create_staff_role(data["role_name"])
            return jsonify(result)
        except Exception as e:
            print(f"[API] 新增角色失败: {e}")
            return jsonify({"ok": False, "reason": str(e)}), 500
    elif request.method == "PUT":
        data = request.get_json(silent=True)
        if not data or not data.get("role_name") or not data.get("role_id"):
            return jsonify({"ok": False, "reason": "参数不完整"}), 400
        try:
            result = db_service.update_staff_role(data["role_id"], data["role_name"])
            if not result.get("ok"):
                return jsonify(result), 400
            return jsonify(result)
        except Exception as e:
            print(f"[API] 编辑角色失败: {e}")
            return jsonify({"ok": False, "reason": str(e)}), 500
    elif request.method == "DELETE":
        role_id = request.args.get("role_id", 0, type=int)
        if not role_id:
            return jsonify({"ok": False, "reason": "role_id 不能为空"}), 400
        try:
            result = db_service.delete_staff_role(role_id)
            if not result.get("ok"):
                return jsonify(result), 400
            return jsonify(result)
        except Exception as e:
            print(f"[API] 删除角色失败: {e}")
            return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/role-tags", methods=["GET", "POST", "DELETE"])
def staff_role_tags():
    """角色标签管理：GET 列表 / POST 新增 / DELETE 删除"""
    if request.method == "GET":
        try:
            return jsonify(db_service.get_role_tags())
        except Exception as e:
            print(f"[API] 获取标签列表失败: {e}")
            return jsonify([]), 500
    elif request.method == "POST":
        data = request.get_json(silent=True)
        if not data or not data.get("tag_name"):
            return jsonify({"ok": False, "reason": "标签名不能为空"}), 400
        tag_color = data.get("tag_color", "#3b82f6")
        try:
            result = db_service.create_role_tag(data["tag_name"], tag_color)
            return jsonify(result)
        except Exception as e:
            print(f"[API] 新增标签失败: {e}")
            return jsonify({"ok": False, "reason": str(e)}), 500
    elif request.method == "DELETE":
        tag_id = request.args.get("tag_id", 0, type=int)
        if not tag_id:
            return jsonify({"ok": False, "reason": "tag_id 不能为空"}), 400
        try:
            result = db_service.delete_role_tag(tag_id)
            return jsonify(result)
        except Exception as e:
            print(f"[API] 删除标签失败: {e}")
            return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/roles/tag", methods=["POST"])
def staff_role_set_tag():
    """为角色设置标签"""
    data = request.get_json(silent=True)
    if not data or not data.get("role_id"):
        return jsonify({"ok": False, "reason": "参数不完整"}), 400
    tag_id = data.get("tag_id", 0)
    try:
        result = db_service.set_role_tag(data["role_id"], tag_id)
        return jsonify(result)
    except Exception as e:
        print(f"[API] 设置角色标签失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/staff/roles/tags", methods=["POST"])
def staff_role_set_tags():
    """为角色设置多个标签（tag_ids: 数组）"""
    data = request.get_json(silent=True)
    if not data or not data.get("role_id"):
        return jsonify({"ok": False, "reason": "参数不完整"}), 400
    tag_ids = data.get("tag_ids", [])
    try:
        result = db_service.set_role_tags(data["role_id"], tag_ids)
        return jsonify(result)
    except Exception as e:
        print(f"[API] 设置角色多标签失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/servers/metrics", methods=["GET"])
def servers_metrics():
    """监控大盘数据（从数据库读取最新记录）"""
    try:
        metrics = db_service.get_latest_metrics()
        if metrics is None:
            return jsonify({"error": "暂无监控数据"}), 404
        return jsonify({"metrics": metrics, "timestamp": "实时查询"})
    except Exception as e:
        print(f"[DB] 查询监控数据失败: {e}")
        return jsonify({"error": "数据库查询失败"}), 500


@app.route("/api/servers/metrics/history", methods=["GET"])
def servers_metrics_history():
    """获取历史监控趋势数据（供前端折线图使用）"""
    limit = request.args.get("limit", 20, type=int)
    try:
        history = db_service.get_historical_metrics(limit)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        print(f"[API] 获取历史监控数据失败: {e}")
        return jsonify({"error": "获取数据失败"}), 500


@app.route("/api/tickets/update", methods=["POST"])
def tickets_update():
    """修改工单（状态和/或优先级，写入数据库）"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求体不能为空"}), 400

    ticket_id = data.get("id")
    if not ticket_id:
        return jsonify({"error": "请提供 id"}), 400

    new_status = data.get("status")
    new_priority = data.get("priority")
    new_description = data.get("description")

    try:
        # 转为字符串直接传递（支持 TKT-YYYYMMDD-XXXX 格式）
        ticket_id = str(ticket_id).strip()

        result = db_service.update_ticket(ticket_id, status=new_status, priority=new_priority, description=new_description)
        if not result.get("ok"):
            return jsonify({"error": result.get("reason", "更新失败")}), 400
        return jsonify({"success": True, "message": result.get("message", ""), "ticket": result.get("ticket")})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[API] 更新工单失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tickets/create", methods=["POST"])
def tickets_create():
    """新建工单"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "reason": "请求体不能为空"}), 400

    title = data.get("title", "").strip()
    priority = data.get("priority", "").strip()
    assignee = data.get("assignee", "").strip()
    status = data.get("status", "未完成")
    description = data.get("description", "").strip()

    # 读取工单新建规则配置
    cfg_desc_required = db_service.get_config_value("ticket_desc_required", "0") == "1"
    cfg_default_priority = db_service.get_config_value("ticket_default_priority", "") or "中"
    try:
        cfg_desc_max = int(db_service.get_config_value("ticket_desc_max_chars", "500"))
    except ValueError:
        cfg_desc_max = 500

    if not title:
        return jsonify({"ok": False, "reason": "工单标题不能为空"}), 400
    if not assignee:
        return jsonify({"ok": False, "reason": "负责人不能为空"}), 400

    # 应用配置：默认优先级
    if not priority or priority not in ("高", "中", "低"):
        priority = cfg_default_priority

    # 应用配置：强制填写描述
    if cfg_desc_required and not description:
        return jsonify({"ok": False, "reason": "系统要求必须填写工单描述"}), 400

    # 应用配置：描述最大字符数
    if len(description) > cfg_desc_max:
        description = description[:cfg_desc_max]

    try:
        result = db_service.create_ticket(title=title, priority=priority, assignee=assignee, status=status, description=description)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result), 201
    except Exception as e:
        print(f"[API] 新建工单失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/tickets/<tid>/delete", methods=["POST"])
def tickets_delete_by_id(tid):
    """删除工单（仅允许删除未完成的工单）"""
    try:
        result = db_service.delete_ticket(tid)
        if result.get("ok"):
            return jsonify({"ok": True, "message": f"已删除工单「{result['title']}」"})
        return jsonify({"ok": False, "reason": result.get("reason", "删除失败")}), 400
    except Exception as e:
        print(f"[API] 删除工单失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/tickets/<tid>/history", methods=["GET"])
def tickets_history(tid):
    """获取工单历史记录"""
    try:
        history = db_service.get_ticket_history(tid)
        return jsonify({"ok": True, "data": history})
    except Exception as e:
        print(f"[API] 获取工单历史失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/tickets/<tid>/candidates", methods=["GET"])
def tickets_candidates(tid):
    """获取可指派的候选人列表"""
    try:
        candidates = db_service.get_assign_candidates(tid)
        return jsonify({"ok": True, "data": candidates})
    except Exception as e:
        print(f"[API] 获取候选人失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


@app.route("/api/tickets/<tid>/assign", methods=["POST"])
def tickets_assign(tid):
    """指派工单"""
    data = request.get_json(silent=True)
    if not data or not data.get("assignee"):
        return jsonify({"ok": False, "reason": "请提供 assignee 参数"}), 400
    try:
        result = db_service.assign_ticket(tid, data["assignee"].strip())
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        print(f"[API] 指派工单失败: {e}")
        return jsonify({"ok": False, "reason": str(e)}), 500


# ========== 调试接口 ==========

@app.route("/api/tickets/<tid>", methods=["GET"])
def get_ticket(tid):
    """查看单个工单状态（从数据库读取）"""
    ticket = db_service.get_ticket_by_id(tid)
    if ticket:
        return jsonify(ticket)
    return jsonify({"error": f"工单 {tid} 不存在"}), 404


@app.route("/api/tickets/search", methods=["POST"])
def search_tickets_advanced():
    """
    多条件动态搜索工单（语音搜索后端入口）
    Body JSON: 直接传给 db_service.search_tickets_dynamic(params)
    返回:
      {
        "code": 200,
        "data": [tickets...],
        "total": N,
        "applied_filters": {...实际生效的过滤项...}
      }
    """
    data = request.get_json(silent=True) or {}
    try:
        result = db_service.search_tickets_dynamic(data)
        return jsonify({
            "code": 200,
            "data": result.get("tickets", []),
            "total": result.get("total", 0),
            "applied_filters": result.get("applied_filters", {}),
        })
    except Exception as e:
        print(f"[search] 失败: {e}")
        return jsonify({"code": 500, "error": str(e)}), 500


@app.route("/api/debug/pending", methods=["GET"])
def debug_pending():
    """查看当前待确认操作（调试用）"""
    return jsonify({
        "has_pending": pending_operation is not None,
        "pending": pending_operation,
        "history_count": len(chat_history),
    })


# ========== 统一错误处理 ==========

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "接口不存在"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "服务器内部错误"}), 500


# ========== 入口 ==========

if __name__ == "__main__":
    print("🚀 数字人智能助手后端启动中...")
    print(f"   🌐 本地: http://127.0.0.1:5000")
    print(f"   🌐 网络: http://172.16.110.204:5000")

    # 预加载 ASR 模型（避免首次请求卡顿，带重试机制应对 Windows Defender 慢扫描）
    print("[启动] 正在预加载 ASR 模型...")
    asr_loaded = False
    for retry in range(1, 4):
        try:
            asr_service.get_model()
            print("[启动] ✅ ASR 模型就绪")
            asr_loaded = True
            break
        except ImportError as e:
            if retry < 3:
                print(f"[启动] ⏳ 第 {retry} 次尝试失败，3 秒后重试...（Windows Defender 扫描中）")
                import time
                time.sleep(3)
            else:
                print(f"[启动] ⚠️ ASR 预加载失败（首次请求时再加载）: {e}")
        except Exception as e:
            print(f"[启动] ⚠️ ASR 预加载失败（首次请求时再加载）: {e}")
            break

    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)