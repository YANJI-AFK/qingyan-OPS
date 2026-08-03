"""测试 context_str 是否影响意图解析"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ollama_service import understand_intent
from chat_state import ChatState

# 模拟一次完整对话：先打招呼，再说打开监控
cs = ChatState()

# 第一轮：你好
cs.context.add_turn("user", "你好")
cs.start_processing()
ctx1 = cs.context.to_prompt_context()
result1 = understand_intent("你好", context_str=ctx1)
print(f"第一轮 [你好]: intent={result1.get('intent')}, params={result1.get('params')}")

# 模拟回复后
cs.context.add_turn("assistant", "你好！我是助手")
cs.state = "IDLE"

# 第二轮：打开监控
cs.context.add_turn("user", "打开监控")
cs.start_processing()
ctx2 = cs.context.to_prompt_context()
print(f"\n上下文: {ctx2[:200]}")
result2 = understand_intent("打开监控", context_str=ctx2)
print(f"\n第二轮 [打开监控]: intent={result2.get('intent')}, params={result2.get('params')}")
