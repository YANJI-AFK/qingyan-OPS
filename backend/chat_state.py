"""
轻言OPS — 对话状态机

管理多轮对话的状态流转，替代原有的简单 chat_history 列表，
实现严谨的确认 / 澄清 / 执行流程。
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

# ============================================================
# 状态定义
# ============================================================

State = Literal["IDLE", "PROCESSING", "REPLYING", "AWAITING_CONFIRMATION", "EXECUTING"]

# 合法的状态转换
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "IDLE":                    {"PROCESSING"},
    "PROCESSING":              {"REPLYING", "AWAITING_CONFIRMATION", "IDLE", "PROCESSING"},
    "REPLYING":                {"IDLE"},
    "AWAITING_CONFIRMATION":   {"EXECUTING", "IDLE"},
    "EXECUTING":               {"IDLE"},
}


# ============================================================
# 对话上下文
# ============================================================

@dataclass
class ChatContext:
    """封装当前对话轮的上下文信息"""

    # 对话历史（最近 20 轮，每轮包含 role + content）
    history: list[dict] = field(default_factory=list)

    # 待确认的操作（如修改工单状态）
    pending_operation: Optional[dict] = None
    # 进入"待确认"状态的时间戳（秒，time.time()）— 用于超时自动取消
    pending_operation_ts: Optional[float] = None

    # 当前意图解析结果
    intent: Optional[str] = None
    intent_data: Optional[dict] = None

    # 上轮追踪的实体（用于指代消解，如"它" → 上轮提到的工单 ID）
    last_entity: Optional[dict] = None

    # 二次确认超时时长（秒）。语音场景下给 30s 比较自然——
    # 留足思考时间，又不至于让一个待确认操作悬空挂太久。
    PENDING_TIMEOUT_SEC: int = 30

    def add_turn(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def recent(self, n: int = 6) -> list[dict]:
        return self.history[-n:]

    def is_pending_expired(self, now: Optional[float] = None) -> bool:
        """检查"待确认"操作是否已超时（超过 PENDING_TIMEOUT_SEC 秒未确认）"""
        if self.pending_operation is None or self.pending_operation_ts is None:
            return False
        import time
        if now is None:
            now = time.time()
        return (now - self.pending_operation_ts) > self.PENDING_TIMEOUT_SEC

    def clear_pending(self) -> None:
        """清除待确认状态（同时清掉时间戳，释放"待确认"占用的资源）"""
        self.pending_operation = None
        self.pending_operation_ts = None
        self.last_entity = None

    def to_prompt_context(self) -> str:
        """将最近对话转为 Prompt 可用的上下文文本"""
        if not self.history:
            return "（无历史对话）"
        lines = ["【对话历史】"]
        for h in self.recent(8):
            role = "用户" if h["role"] == "user" else "助手"
            lines.append(f"{role}：{h['content']}")
        if self.last_entity:
            e = self.last_entity
            if e.get("type") == "ticket_stat":
                label = e.get("status_label", "")
                total = e.get("total", 0)
                fs = e.get("filter_status", "")
                fp = e.get("filter_priority", "")
                sd = e.get("start_date", "")
                ed = e.get("end_date", "")
                cond = []
                if fs: cond.append(fs)
                if fp: cond.append(f"{fp}优先级")
                if sd and ed:
                    if sd == ed:
                        cond.append(f"日期{sd}")
                    else:
                        cond.append(f"日期{sd}至{ed}")
                cond_str = "·".join(cond) if cond else "所有"
                date_hint = f"（start_date={sd}, end_date={ed}）" if sd and ed else ""
                lines.append(f"【上下文提示】上一轮用户查询了{cond_str}工单（共{total}个）{date_hint}。如果用户说「其中」「里面」等指代词，必须继承上一轮的全部条件（包括日期、状态），仅追加或替换新条件。")
            elif e.get("type") == "ticket_search":
                applied = e.get("applied_filters", {})
                total = e.get("total", 0)
                cond = "、".join(f"{k}={v}" for k, v in applied.items()) or "指定条件"
                lines.append(f"【上下文提示】上一轮搜索了{cond}的工单（共{total}条）。如果用户说「其中」「里面」等指代词，请基于上一轮的条件继续筛选。")
            else:
                lines.append(f"【上下文提示】上轮讨论了: {e}")
        return "\n".join(lines)


# ============================================================
# 状态机
# ============================================================

class ChatState:
    """对话状态机 — 管理多轮对话的生命周期"""

    def __init__(self):
        self.state: State = "IDLE"
        self.context = ChatContext()
        self._transition_log: list[str] = []

    # -------- 状态查询 --------
    @property
    def is_idle(self) -> bool:
        return self.state == "IDLE"

    @property
    def is_awaiting_confirmation(self) -> bool:
        return self.state == "AWAITING_CONFIRMATION"

    # -------- 状态转换 --------
    def transition(self, new_state: State) -> None:
        if new_state not in ALLOWED_TRANSITIONS.get(self.state, set()):
            raise ValueError(
                f"非法状态转换: {self.state} -> {new_state}。"
                f"允许: {ALLOWED_TRANSITIONS.get(self.state, set())}"
            )
        old = self.state
        self.state = new_state
        self._transition_log.append(f"{old} -> {new_state}")
        if len(self._transition_log) > 50:
            self._transition_log = self._transition_log[-50:]

    # -------- 业务方法 --------

    def start_processing(self) -> None:
        """进入处理中状态（如已在处理中则跳过）"""
        if self.state == "PROCESSING":
            return  # 幂等，已在处理中
        self.transition("PROCESSING")

    def reply_and_idle(self) -> None:
        """回复完成，回到空闲"""
        self.transition("REPLYING")
        self.transition("IDLE")

    def await_confirmation(self, operation: dict, entity: dict | None = None) -> None:
        """进入等待确认状态，保存待确认操作，并记录开始时间用于超时清理"""
        import time
        self.context.pending_operation = operation
        if entity:
            self.context.last_entity = entity
        self.context.pending_operation_ts = time.time()
        self.transition("AWAITING_CONFIRMATION")

    def confirm_and_execute(self) -> dict:
        """用户确认 → 进入执行状态"""
        self.transition("EXECUTING")
        op = self.context.pending_operation or {}
        return op

    def cancel_and_idle(self) -> None:
        """用户取消 → 清理并回到空闲"""
        self.context.clear_pending()
        self.transition("IDLE")

    def handle_confirmation_input(self, text: str) -> Optional[bool]:
        """
        检测用户输入是否为确认/取消
        返回 True=确认, False=取消, None=其他
        """
        t = text.strip().lower()
        confirm_words = ["确认", "是", "确定", "可以", "好", "行", "对", "yes", "ok", "执行",
                         "正确", "没错", "对", "嗯", "继续", "就这么办", "就这样"]
        cancel_words = ["取消", "否", "不", "算了", "不要", "别", "no", "cancel", "放弃",
                        "停止", "中止", "不了", "不必了", "不用"]
        # 优先精确匹配：单字/词直接命中
        if t in confirm_words:
            return True
        if t in cancel_words:
            return False
        # 模糊包含匹配
        if any(w in t for w in confirm_words):
            return True
        if any(w in t for w in cancel_words):
            return False
        return None

    # -------- 调试 --------
    def dump(self) -> dict:
        return {
            "state": self.state,
            "history_len": len(self.context.history),
            "pending": self.context.pending_operation,
            "last_entity": self.context.last_entity,
            "transitions": self._transition_log[-10:],
        }
