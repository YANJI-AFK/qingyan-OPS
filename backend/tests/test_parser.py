"""测试 ollama_service 的 JSON 解析和意图清理"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ollama_service import _parse_llm_json, _clean_intent

# 测试用例
tests = [
    # 正常 JSON
    ('{"intent":"navigate","api":"navigate","params":{"target":"/tickets"}}', "navigate"),
    # 管道符 intent
    ('{"intent":"navigate|query","api":"navigate","params":{"target":"/tickets"}}', "navigate"),
    # markdown 代码块 + 管道符
    ('```json\n{"intent":"navigate|query","api":"navigate","params":{"target":"/tickets"}}\n```', "navigate"),
    # 多行 markdown + 错误 target(中文)
    ('```json\n{\n  "intent": "navigate",\n  "api": "navigate",\n  "params": {\n    "target": "/tickets"\n  }\n}\n```', "navigate"),
    # 标准 query
    ('{"intent":"query","api":"tickets_stat","params":{"status":"未完成"}}', "query"),
    # greeting
    ('{"intent":"greeting","params":{}}', "greeting"),
    # 空
    ('', "error"),
]

all_pass = True
for raw, expected in tests:
    result = _parse_llm_json(raw)
    got = result.get("intent", "error")
    status = "PASS" if got == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"[{status}] intent={got:12s} (expected={expected})")

print(f"\n{'ALL PASS' if all_pass else 'SOME FAILED'}")
