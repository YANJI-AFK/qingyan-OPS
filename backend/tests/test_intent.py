"""测试完整 understand_intent 流程"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ollama_service import understand_intent

for text in ["打开监控大屏", "打开监控", "跳转到工单列表", "回到首页", "你好"]:
    result = understand_intent(text)
    print(f"\n{'='*50}")
    print(f"输入: {text}")
    print(f"结果: {result}")
