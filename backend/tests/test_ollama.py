import requests, json

payload = {
    "model": "qwen2.5:7b-instruct-q4_K_M",
    "prompt": "你是一个意图解析器。用户说：跳转到工单列表。请输出JSON：",
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 200},
}
print("Sending request to Ollama...")
r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
d = r.json()
print(f"done={d.get('done')}, done_reason={d.get('done_reason')}, eval_count={d.get('eval_count')}")
print(f"response: {repr(d.get('response', ''))}")
print(f"full keys: {list(d.keys())}")

# Test 2: with long system prompt
long_prompt = (
    "你是一个意图解析器，只输出一行 JSON，绝不输出任何其他文字。\n"
    '格式：{"intent":"navigate|query|greeting|unknown","api":"...","params":{...}}\n'
    "示例：\n"
    '  打开监控 → {"intent":"navigate","api":"navigate","params":{"target":"/monitor"}}\n'
    '  跳转到工单列表 → {"intent":"navigate","api":"navigate","params":{"target":"/tickets"}}\n'
    "用户说：跳转到工单列表。\n请输出 JSON："
)
payload2 = {
    "model": "qwen2.5:7b-instruct-q4_K_M",
    "prompt": long_prompt,
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 200},
}
print("\n--- Test 2: Long prompt ---")
r2 = requests.post("http://localhost:11434/api/generate", json=payload2, timeout=30)
d2 = r2.json()
print(f"done={d2.get('done')}, done_reason={d2.get('done_reason')}, eval_count={d2.get('eval_count')}")
print(f"response: {repr(d2.get('response', ''))}")
